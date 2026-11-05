from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('changomas', '0006_alert_delivery')]
    operations = [migrations.CreateModel(name='RateWindow', fields=[
        ('key', models.CharField(max_length=120, primary_key=True, serialize=False)),
        ('attempts', models.PositiveIntegerField(default=0)),
        ('expires_at', models.DateTimeField(db_index=True)),
    ])]
