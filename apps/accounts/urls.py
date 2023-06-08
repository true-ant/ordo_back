from django.urls import include, path
from rest_framework_nested.routers import NestedSimpleRouter, SimpleRouter

import apps.accounts.views.company
import apps.accounts.views.company_member
import apps.accounts.views.health
import apps.accounts.views.invitation_check
import apps.accounts.views.office
import apps.accounts.views.office_budget
import apps.accounts.views.office_vendor
import apps.accounts.views.user
import apps.accounts.views.user_signup
import apps.accounts.views.vendor
import apps.accounts.views.vendor_request

router = SimpleRouter(trailing_slash=False)
router.register(r"companies", apps.accounts.views.company.CompanyViewSet, basename="companies")
router.register(r"vendors", apps.accounts.views.vendor.VendorViewSet, basename="vendors")
router.register(r"users", apps.accounts.views.user.UserViewSet, basename="users")

company_router = NestedSimpleRouter(router, r"companies", lookup="company")
company_router.register(r"members", apps.accounts.views.company_member.CompanyMemberViewSet, basename="members")
company_router.register(r"offices", apps.accounts.views.office.OfficeViewSet, basename="offices")
company_router.register(
    r"vendor-requests", apps.accounts.views.vendor_request.VendorRequestViewSet, basename="vendor-requests"
)

office_router = NestedSimpleRouter(company_router, r"offices", lookup="office")
office_router.register(r"vendors", apps.accounts.views.office_vendor.OfficeVendorViewSet, basename="vendors")
office_router.register(r"budgets", apps.accounts.views.office_budget.BudgetViewSet, basename="budgets")

urlpatterns = [
    path("health/check", apps.accounts.views.health.HealthCheck.as_view()),
    path("", include(router.urls)),
    path("", include(company_router.urls)),
    path("", include(office_router.urls)),
    path("auth/signup", apps.accounts.views.user_signup.UserSignupAPIView.as_view(), name="signup"),
    path(
        "accept-invite/<str:token>", apps.accounts.views.invitation_check.CompanyMemberInvitationCheckAPIView.as_view()
    ),
]
