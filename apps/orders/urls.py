from django.urls import include, path
from rest_framework_nested.routers import NestedSimpleRouter, SimpleRouter

from apps.accounts.urls import company_router

from . import views as v

router = SimpleRouter(trailing_slash=False)
# router.register(r"products", v.ProductViewSet, basename="products")
router.register(r"products", v.ProductViewSet)
router.register(r"products-data", v.ProductDataViewSet)
router.register(r"v2/products", v.ProductV2ViewSet)

offices_router = NestedSimpleRouter(company_router, r"offices", lookup="office")
offices_router.register(r"orders", v.OrderViewSet, basename="orders")
offices_router.register(r"vendor-orders", v.VendorOrderViewSet, basename="vendor-orders")

offices_router.register(r"order-products", v.VendorOrderProductViewSet, basename="order-products")
# offices_router.register(r"inventory-products", v.InventoryProductViewSet, basename="inventory-products")
offices_router.register(r"carts", v.CartViewSet, basename="carts")
offices_router.register(r"products", v.OfficeProductViewSet, basename="products")
offices_router.register(r"product-categories", v.OfficeProductCategoryViewSet, basename="product-categories")

offices_router.register(r"procedures", v.ProcedureViewSet, basename="procedures")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(offices_router.urls)),
    path("companies/<int:company_pk>/spending", v.CompanySpendAPIView.as_view(), name="company-spending"),
    path("offices/<int:office_pk>/spending", v.OfficeSpendAPIView.as_view(), name="office-spending"),
    path(
        "companies/<int:company_pk>/offices/<int:office_pk>/checkout/status",
        v.CheckoutAvailabilityAPIView.as_view(),
        name="get-checkout-status",
    ),
    path(
        "companies/<int:company_pk>/offices/<int:office_pk>/checkout/update-status",
        v.CheckoutUpdateStatusAPIView.as_view(),
        name="update-checkout-status",
    ),
    path(
        "companies/<int:company_pk>/offices/<int:office_pk>/search-products",
        v.SearchProductAPIView.as_view(),
        name="search-products",
    ),
]
