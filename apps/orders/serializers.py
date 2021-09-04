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
    total_items = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = m.Order
        fields = ("id", "order_id", "total_amount", "currency", "order_date", "status", "total_items")


class CompanyVendorConnectedSerializer(serializers.Serializer):
    company_associated_id = serializers.CharField()
    id = serializers.CharField()
    name = serializers.CharField()


class TotalSpendSerializer(serializers.Serializer):
    vendor = CompanyVendorConnectedSerializer(read_only=True)
    month = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
