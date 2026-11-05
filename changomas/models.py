import re

from django.core.exceptions import ValidationError
from django.db import models

# Largo GTIN válido: EAN-8, UPC-A (12), EAN-13, GTIN-14. Solo estos EANs
# sirven para matchear el mismo producto entre tiendas.
GTIN_RE = re.compile(r'^(\d{8}|\d{12}|\d{13}|\d{14})$')

# Segmentos de URL que no pueden usarse como slug de tienda.
RESERVED_SLUGS = {'comparador', 'carrito', 'ofertas', 'cuenta', 'seguimientos', 'api', 'producto', 'escanear'}


class Supermarket(models.Model):
    """Cadena relevada por el tracker.

    El slug es estable y se usa tanto en las URLs como en la API. La
    configuracion tecnica de VTEX vive en ``scraper.py``; este modelo guarda
    solamente los datos publicos que necesita la UI.
    """

    slug = models.SlugField(max_length=32, primary_key=True)
    name = models.CharField(max_length=80)
    base_url = models.URLField(max_length=300)
    primary_color = models.CharField(max_length=7, default='#0071ce')
    accent_color = models.CharField(max_length=7, default='#ffc220')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.slug in RESERVED_SLUGS:
            raise ValidationError(
                {'slug': f"'{self.slug}' está reservado por las URLs del comparador."}
            )


class CatalogItem(models.Model):
    gtin = models.CharField(max_length=14, unique=True)
    name = models.CharField(max_length=300)
    brand = models.CharField(max_length=150, blank=True)


class SourceRun(models.Model):
    supermarket = models.ForeignKey(Supermarket, on_delete=models.CASCADE, related_name='runs')
    kind = models.CharField(max_length=16, default='catalog')
    status = models.CharField(max_length=16, default='running')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    product_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-started_at']


class Product(models.Model):
    """
    Una publicación de producto dentro de un supermercado.
    El código de referencia es único por cadena: usa el EAN cuando existe
    y, en caso contrario, la referencia VTEX con prefijo ``vtex-``.
    """
    supermarket = models.ForeignKey(
        Supermarket,
        on_delete=models.PROTECT,
        related_name='products',
        default='changomas',
    )
    reference_code = models.CharField(
        max_length=64, db_index=True,
        help_text="EAN del producto o, si no tiene, 'vtex-<productId>'.",
    )
    ean = models.CharField(max_length=32, blank=True, default='', db_index=True)
    vtex_product_id = models.CharField(max_length=32, db_index=True)
    vtex_sku_id = models.CharField(
        max_length=32, blank=True, null=True, default=None, db_index=True,
    )
    product_reference = models.CharField(max_length=64, blank=True, default='', db_index=True)
    measurement_unit = models.CharField(max_length=16, blank=True, default='')
    unit_multiplier = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    name = models.CharField(max_length=300, db_index=True)
    search_text = models.TextField(blank=True, default='')
    brand = models.CharField(max_length=150, blank=True, default='')
    category = models.CharField(max_length=300, blank=True, default='', db_index=True)
    image_url = models.URLField(max_length=500, blank=True, default='')
    link = models.URLField(max_length=500, blank=True, default='')
    is_available = models.BooleanField(default=True)
    # Precalculado al scrapear (EAN con largo GTIN válido): el comparador
    # filtra por este flag indexado en vez de evaluar un regex por request.
    is_comparable = models.BooleanField(default=False, db_index=True)
    catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL, related_name='listings')
    last_price_checked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['supermarket', 'reference_code'],
                name='unique_reference_per_supermarket',
            ),
            models.UniqueConstraint(
                fields=['supermarket', 'vtex_sku_id'],
                name='unique_vtex_sku_per_supermarket',
            ),
        ]
        indexes = [
            models.Index(fields=['supermarket', 'ean'], name='product_store_ean_idx'),
            models.Index(
                fields=['supermarket', 'vtex_product_id'],
                name='product_store_vtex_idx',
            ),
        ]

    def __str__(self):
        return f"{self.supermarket.name}: {self.name} ({self.reference_code})"

    def save(self, *args, **kwargs):
        from .search import normalize
        self.search_text = normalize(self.name + ' ' + self.brand)
        from .pricing import normalize_gtin
        gtin = normalize_gtin(self.ean)
        if gtin:
            if not self.catalog_item_id or self.catalog_item.gtin != gtin:
                self.catalog_item, _ = CatalogItem.objects.get_or_create(gtin=gtin, defaults={'name': self.name, 'brand': self.brand})
        else:
            self.catalog_item = None
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'search_text', 'catalog_item'}
        return super().save(*args, **kwargs)

    @property
    def latest_price(self):
        return self.prices.order_by('-date').first()


class PriceRecord(models.Model):
    """
    Precio de un producto en un día dado. Se guarda una fila por
    producto por día y se purgan los registros de más de 30 días.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='prices')
    date = models.DateField(db_index=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    promotion = models.JSONField(default=dict, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    list_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    promo_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Precio efectivo por unidad aplicando la promo "
                  "(ej: 50% la 2da unidad => 25% de descuento real).",
    )
    promo_text = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['product', 'date'], name='unique_price_per_day'),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.date}: ${self.price}"

    @property
    def promotion_label(self):
        from .pricing import promotion_label
        return promotion_label(self)

    @property
    def effective_price(self):
        """El mejor precio unitario del día (promo si existe, si no el precio común)."""
        if self.promo_price is not None and self.promo_price < self.price:
            return self.promo_price
        return self.price

    @property
    def discount_percent(self):
        """Descuento del precio común contra el precio de lista, en %."""
        if self.list_price and self.list_price > self.price:
            return round((1 - self.price / self.list_price) * 100)
        return 0


class PriceObservation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='observations')
    source_run = models.ForeignKey(SourceRun, on_delete=models.SET_NULL, null=True, blank=True)
    observed_at = models.DateTimeField(db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    list_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    promo_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    promo_text = models.CharField(max_length=200, blank=True)
    promotion = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        ordering = ['-observed_at', '-pk']
        indexes = [models.Index(fields=['product', '-observed_at'])]


from .personal_models import ShoppingCart, CartItem, Subscription, NotificationPreference, RateWindow  # noqa: E402,F401
from .alert_models import PriceAlertEvent, EmailDelivery, JobLease  # noqa: E402,F401
