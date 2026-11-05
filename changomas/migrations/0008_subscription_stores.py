from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ('changomas', '0007_rate_windows'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='stores',
            field=models.ManyToManyField(blank=True, related_name='subscribers', to='changomas.supermarket'),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='verified_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gte', 1), ('quantity__lte', 99)), name='cart_item_quantity_1_99'),
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.CheckConstraint(condition=models.Q(('target_price__isnull', True), ('target_price__gt', 0), _connector='OR'), name='subscription_target_price_positive'),
        ),
    ]
