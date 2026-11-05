from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ShoppingCart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shopping_cart'
    )
    version = models.PositiveIntegerField(default=1)
    # Import IDs make a guest-cart merge safe to retry after a lost response.
    imported_batches = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f'Carrito de {self.user}'


class CartItem(models.Model):
    cart = models.ForeignKey(ShoppingCart, on_delete=models.CASCADE, related_name='items')
    ean = models.CharField(max_length=32)
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(99)]
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=['cart', 'ean'], name='unique_cart_ean')]
        constraints += [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=99),
                name='cart_item_quantity_1_99',
            ),
        ]
        ordering = ['ean']


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    product = models.ForeignKey('changomas.Product', on_delete=models.CASCADE, related_name='subscriptions')
    stores = models.ManyToManyField(
        'changomas.Supermarket', blank=True, related_name='subscribers'
    )
    target_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0.01)],
    )
    promo_alert = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_condition = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_user_product_subscription'),
            models.CheckConstraint(
                condition=models.Q(target_price__isnull=True) | models.Q(target_price__gt=0),
                name='subscription_target_price_positive',
            ),
        ]
        ordering = ['-created_at']


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preference'
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    verified_email = models.EmailField(blank=True, default='')
    email_enabled = models.BooleanField(default=False)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Preferencias de {self.user}'


class RateWindow(models.Model):
    key = models.CharField(max_length=120, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
