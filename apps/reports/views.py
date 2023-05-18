import csv
import io
from django.utils import timezone

from django.http import HttpResponse, FileResponse
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Office, User, CompanyMember
from apps.reports.formatters.csv import export_to_csv
from apps.reports.services.inventory_list import inventory_list


class InventoryListAPIView(APIView):
    def get(self, request, **kwargs):
        office_id = request.query_params.get("office_id")
        user: User = request.user
        office = Office.objects.filter(pk=office_id).first()
        if not office:
            raise ValidationError("Office does not exist")
        if not CompanyMember.objects.filter(office_id=office.id, user=user).exists():
            raise PermissionDenied("User does not have permissions to access this endpoint")
        rows = inventory_list(office_id)
        date_str = timezone.now().strftime("%Y%m%d%H%M")
        return FileResponse(
            export_to_csv(rows),
            as_attachment=True,
            filename=f"{office.name}-{date_str}.csv",
            content_type="text/csv"
        )
