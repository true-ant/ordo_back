from django.urls import include, path
from rest_framework_nested.routers import NestedSimpleRouter

from apps.accounts.urls import company_router

from . import views as v

offices_router = NestedSimpleRouter(company_router, r"offices", lookup="office")
offices_router.register(r"orders", v.OrderViewSet, basename="orders")

urlpatterns = [
    path("", include(offices_router.urls)),
]
