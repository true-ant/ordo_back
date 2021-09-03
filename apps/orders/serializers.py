from rest_framework import serializers

from apps.accounts.serializers import VendorSerializer

from . import models as m


class ProductSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer()

    class Meta:
        model = m.Product
        fields = "__all__"


class OrderProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = m.OrderProduct
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    products = OrderProductSerializer(many=True, source="orderproduct_set")

    class Meta:
        model = m.Order
        fields = "__all__"


class OrderListSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Order
        exclude = ("products",)
