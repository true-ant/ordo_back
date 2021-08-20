from django.urls import include, path
from rest_framework_nested.routers import NestedSimpleRouter, SimpleRouter

from . import views as v

router = SimpleRouter(trailing_slash=False)
router.register(r"orders", v.OrderViewSet, basename="orders")


order_router = NestedSimpleRouter(router, r"orders", lookup="order")
order_router.register(r"items", v.OrderItemViewSet, basename="items")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(order_router.urls)),
]
