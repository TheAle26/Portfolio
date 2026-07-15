from django.contrib import admin

from .models import PriceRecord, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'name', 'brand', 'category', 'is_available', 'last_seen')
    list_filter = ('is_available',)
    search_fields = ('reference_code', 'ean', 'name', 'brand', 'vtex_product_id')


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ('product', 'date', 'price', 'list_price', 'promo_price', 'promo_text')
    list_filter = ('date',)
    search_fields = ('product__name', 'product__reference_code')
    raw_id_fields = ('product',)
    date_hierarchy = 'date'
