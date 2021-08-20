from rest_framework import serializers

from . import models as m


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OrderItem
        exclude = ("order",)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = m.Order
        field = "__all__"
