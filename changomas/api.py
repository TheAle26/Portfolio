from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import PriceRecord, Product, Supermarket
from .serializers import (
    ProductDetailSerializer,
    ProductListSerializer,
    SupermarketSerializer,
)


class ProductPagination(PageNumberPagination):
    page_size = 48
    page_size_query_param = 'page_size'
    max_page_size = 100


class SupermarketViewSet(ReadOnlyModelViewSet):
    serializer_class = SupermarketSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        return (
            Supermarket.objects.filter(is_active=True)
            .annotate(product_count=Count('products', filter=Q(products__is_available=True)))
        )


class ProductViewSet(ReadOnlyModelViewSet):
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    pagination_class = ProductPagination
    http_method_names = ['get', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    def get_queryset(self):
        cutoff = timezone.localdate() - timezone.timedelta(days=29)
        prices = PriceRecord.objects.filter(date__gte=cutoff).order_by('-date')
        queryset = (
            Product.objects.filter(supermarket__is_active=True)
            .select_related('supermarket')
            .prefetch_related(Prefetch('prices', queryset=prices, to_attr='api_price_history'))
        )

        store = self.request.query_params.get('store', '').strip()
        if store:
            queryset = queryset.filter(supermarket_id=store)

        default_availability = 'true' if self.action == 'list' else ''
        availability = self.request.query_params.get(
            'available', default_availability,
        ).lower()
        if availability in ('true', '1'):
            queryset = queryset.filter(is_available=True)
        elif availability in ('false', '0'):
            queryset = queryset.filter(is_available=False)

        query = self.request.query_params.get('q', '').strip()[:100]
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(brand__icontains=query)
            )

        category = self.request.query_params.get('category', '').strip()[:100]
        if category:
            queryset = queryset.filter(
                Q(category=category) | Q(category__startswith=category + ' / ')
            )

        ean = self.request.query_params.get('ean', '').strip()[:32]
        if ean:
            queryset = queryset.filter(ean=ean)

        return queryset.order_by('supermarket_id', 'name')
