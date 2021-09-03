from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Company, CompanyMember, Office


class CompanyOfficeReadPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Company):
            return CompanyMember.objects.filter(company=obj, user=request.user)
        elif isinstance(obj, Office):
            return CompanyMember.objects.filter(company=obj.company, user=request.user)
