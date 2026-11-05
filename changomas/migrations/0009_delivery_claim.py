from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('changomas', '0008_subscription_stores')]
    operations = [migrations.AddField(model_name='emaildelivery', name='claimed_at',
        field=models.DateTimeField(null=True, blank=True))]
