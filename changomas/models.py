from django.db import models


class Product(models.Model):
    """
    Un producto del catálogo de MasOnline (ChangoMás).
    El código de referencia único es el EAN si existe; si no, la
    referencia de VTEX (con prefijo 'vtex-') para poder buscar por ambos.
    """
    reference_code = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text="EAN del producto o, si no tiene, 'vtex-<productId>'.",
    )
    ean = models.CharField(max_length=32, blank=True, default='', db_index=True)
    vtex_product_id = models.CharField(max_length=32, unique=True)
    product_reference = models.CharField(max_length=64, blank=True, default='', db_index=True)
    name = models.CharField(max_length=300, db_index=True)
    brand = models.CharField(max_length=150, blank=True, default='')
    category = models.CharField(max_length=300, blank=True, default='', db_index=True)
    image_url = models.URLField(max_length=500, blank=True, default='')
    link = models.URLField(max_length=500, blank=True, default='')
    is_available = models.BooleanField(default=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.reference_code})"

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
