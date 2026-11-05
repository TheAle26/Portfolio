import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('changomas', '0005_personal'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JobLease',
            fields=[
                ('name', models.CharField(max_length=80, primary_key=True, serialize=False)),
                ('token', models.CharField(max_length=32)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='PriceAlertEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64)),
                ('payload', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('observation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_events', to='changomas.priceobservation')),
                ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_events', to='changomas.subscription')),
            ],
            options={'ordering': ['created_at', 'pk']},
        ),
        migrations.AddConstraint(
            model_name='pricealertevent',
            constraint=models.UniqueConstraint(fields=('subscription', 'key'), name='unique_alert_event_key'),
        ),
        migrations.CreateModel(
            name='EmailDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('batch_key', models.CharField(max_length=64, unique=True)),
                ('state', models.CharField(choices=[('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed'), ('uncertain', 'Uncertain')], db_index=True, default='pending', max_length=12)),
                ('body_snapshot', models.JSONField(default=dict)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('next_attempt_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('events', models.ManyToManyField(related_name='deliveries', to='changomas.pricealertevent')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_email_deliveries', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['created_at', 'pk']},
        ),
    ]
