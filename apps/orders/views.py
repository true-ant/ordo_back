from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from . import models as m
from . import serializers as s


class OrderViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderSerializer

    def get_queryset(self):
        return m.Order.objects.filter(office_vendor__office__id=self.kwargs["office_pk"])


class OrderItemViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderItemSerializer

    def get_queryset(self):
        return m.OrderItem.objects.filter(order_id=self.kwargs["order__pk"])
