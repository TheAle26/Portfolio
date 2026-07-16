import django.db.models.deletion
from django.db import migrations, models


SUPERMARKETS = (
    {
        'slug': 'changomas',
        'name': 'ChangoMás',
        'base_url': 'https://www.masonline.com.ar',
        'primary_color': '#0071ce',
        'accent_color': '#ffc220',
    },
    {
        'slug': 'carrefour',
        'name': 'Carrefour',
        'base_url': 'https://www.carrefour.com.ar',
        'primary_color': '#005baa',
        'accent_color': '#e30613',
    },
    {
        'slug': 'disco',
        'name': 'Disco',
        'base_url': 'https://www.disco.com.ar',
        'primary_color': '#ed1c24',
        'accent_color': '#ffd200',
    },
)


def seed_supermarkets(apps, schema_editor):
    Supermarket = apps.get_model('changomas', 'Supermarket')
    for values in SUPERMARKETS:
        Supermarket.objects.update_or_create(slug=values['slug'], defaults=values)


class Migration(migrations.Migration):

    dependencies = [
        ('changomas', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supermarket',
            fields=[
                ('slug', models.SlugField(max_length=32, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80)),
                ('base_url', models.URLField(max_length=300)),
                ('primary_color', models.CharField(default='#0071ce', max_length=7)),
                ('accent_color', models.CharField(default='#ffc220', max_length=7)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.RunPython(seed_supermarkets, migrations.RunPython.noop),
        migrations.AddField(
            model_name='product',
            name='supermarket',
            field=models.ForeignKey(
                default='changomas',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='changomas.supermarket',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='measurement_unit',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
        migrations.AddField(
            model_name='product',
            name='unit_multiplier',
            field=models.DecimalField(decimal_places=4, default=1, max_digits=12),
        ),
        migrations.AddField(
            model_name='product',
            name='vtex_sku_id',
            field=models.CharField(
                blank=True, db_index=True, default=None, max_length=32, null=True,
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='reference_code',
            field=models.CharField(
                db_index=True,
                help_text="EAN del producto o, si no tiene, 'vtex-<productId>'.",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='vtex_product_id',
            field=models.CharField(db_index=True, max_length=32),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                fields=('supermarket', 'reference_code'),
                name='unique_reference_per_supermarket',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                fields=('supermarket', 'vtex_sku_id'),
                name='unique_vtex_sku_per_supermarket',
            ),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['supermarket', 'ean'], name='product_store_ean_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['supermarket', 'vtex_product_id'],
                name='product_store_vtex_idx',
            ),
        ),
    ]
