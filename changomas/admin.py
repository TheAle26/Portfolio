from django.contrib import admin

from .models import PriceRecord, Product, Supermarket


@admin.register(Supermarket)
class SupermarketAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'base_url', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'supermarket', 'reference_code', 'name', 'brand', 'category',
        'is_available', 'last_seen',
    )
    list_filter = ('supermarket', 'is_available')
    search_fields = (
        'reference_code', 'ean', 'name', 'brand', 'vtex_product_id',
        'supermarket__name',
    )


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'supermarket', 'date', 'price', 'list_price',
        'promo_price', 'promo_text',
    )
    list_filter = ('product__supermarket', 'date')
    search_fields = ('product__name', 'product__reference_code')
    raw_id_fields = ('product',)
    date_hierarchy = 'date'

    @admin.display(ordering='product__supermarket', description='Supermercado')
    def supermarket(self, obj):
        return obj.product.supermarket
