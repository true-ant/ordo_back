from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import models as m


class CompanyPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return request.method in SAFE_METHODS or request.user.role == m.User.Role.ADMIN

    def has_object_permission(self, request, view, obj):
        return m.CompanyMember.objects.filter(company=obj, user=request.user).exists()
