from django.db.models import F, Sum
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from . import filters as f
from . import models as m
from . import serializers as s


class OrderViewSet(ModelViewSet):
    queryset = m.Order.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderSerializer
    filterset_class = f.OrderFilter

    def get_queryset(self):
        return super().get_queryset().filter(office_vendor__office__id=self.kwargs["office_pk"])

    @action(detail=False, methods=["get"], url_path="by-vendors")
    def get_statics_by_vendor(self, request, *args, **kwargs):
        qs = self.get_queryset()
        qs = (
            qs.values("office_vendor")
            .order_by("office_vendor")
            .annotate(total_amount=Sum("total_amount"), vendor=F("office_vendor__vendor__name"))
        )
        return Response(qs)


class OrderProductViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.OrderProduct.objects.all()
    serializer_class = s.OrderProductSerializer

    def get_queryset(self):
        return super().get_queryset().filter(order__office_vendor__office__id=self.kwargs["office_pk"])


#
# class OrderItemViewSet(ModelViewSet):
#     permission_classes = [IsAuthenticated]
#     serializer_class = s.OrderItemSerializer
#
#     def get_queryset(self):
#         return m.OrderItem.objects.filter(order_id=self.kwargs["order__pk"])
