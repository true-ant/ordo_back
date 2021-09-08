from django.urls import include, path
from rest_framework_nested.routers import NestedSimpleRouter, SimpleRouter

from . import views as v

router = SimpleRouter(trailing_slash=False)
router.register(r"companies", v.CompanyViewSet, basename="companies")
router.register(r"vendors", v.VendorViewSet, basename="vendors")
router.register(r"users", v.UserViewSet, basename="users")

company_router = NestedSimpleRouter(router, r"companies", lookup="company")
company_router.register(r"members", v.CompanyMemberViewSet, basename="members")
company_router.register(r"offices", v.OfficeViewSet, basename="offices")

office_router = NestedSimpleRouter(company_router, r"offices", lookup="office")
office_router.register(r"vendors", v.OfficeVendorViewSet, basename="vendors")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(company_router.urls)),
    path("", include(office_router.urls)),
    path("auth/signup", v.UserSignupAPIView.as_view(), name="signup"),
    path("accept-invite/<str:token>", v.CompanyMemberInvitationCheckAPIView.as_view()),
]
