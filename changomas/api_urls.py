from rest_framework.routers import DefaultRouter

from .api import ProductViewSet, SupermarketViewSet


app_name = 'supermarkets_api'

router = DefaultRouter()
router.register('stores', SupermarketViewSet, basename='store')
router.register('products', ProductViewSet, basename='product')

urlpatterns = router.urls
