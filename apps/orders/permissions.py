from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.models import Company, CompanyMember, Office


class CompanyOfficeReadPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Company):
            return CompanyMember.objects.filter(company=obj, user=request.user)
        elif isinstance(obj, Office):
            return CompanyMember.objects.filter(company=obj.company, user=request.user)


class OrderCheckoutPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        company_pk = view.kwargs.get("company_pk")
        return CompanyMember.objects.filter(user=request.user, company_id=company_pk).exists()
