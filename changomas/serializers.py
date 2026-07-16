from rest_framework import serializers

from .models import PriceRecord, Product, Supermarket


class SupermarketSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Supermarket
        fields = (
            'slug', 'name', 'base_url', 'primary_color', 'accent_color',
            'product_count',
        )


class SupermarketSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Supermarket
        fields = ('slug', 'name', 'base_url', 'primary_color', 'accent_color')


class PriceRecordSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = PriceRecord
        fields = (
            'date', 'price', 'list_price', 'promo_price', 'promo_text',
            'effective_price', 'discount_percent',
        )


class ProductListSerializer(serializers.ModelSerializer):
    supermarket = SupermarketSummarySerializer(read_only=True)
    latest_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'supermarket', 'reference_code', 'ean', 'vtex_product_id',
            'vtex_sku_id', 'product_reference', 'name', 'brand', 'category',
            'measurement_unit', 'unit_multiplier', 'image_url', 'link',
            'is_available', 'first_seen', 'last_seen', 'latest_price',
        )

    def get_latest_price(self, obj):
        history = getattr(obj, 'api_price_history', None)
        record = history[0] if history else None
        if history is None:
            record = obj.latest_price
        return PriceRecordSerializer(record).data if record else None


class ProductDetailSerializer(ProductListSerializer):
    price_history = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ('price_history', 'stats')

    def get_price_history(self, obj):
        records = getattr(obj, 'api_price_history', [])
        return PriceRecordSerializer(records, many=True).data

    def get_stats(self, obj):
        records = getattr(obj, 'api_price_history', [])
        if not records:
            return None
        effective_prices = [record.effective_price for record in records]
        return {
            'days': len(records),
            'minimum_effective_price': min(effective_prices),
            'maximum_effective_price': max(effective_prices),
            'current_effective_price': records[0].effective_price,
        }
