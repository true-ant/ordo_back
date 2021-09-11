from django.db import transaction
from rest_framework import serializers

from apps.accounts.serializers import VendorSerializer

from . import models as m


class ProductSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer()

    class Meta:
        model = m.Product
        fields = "__all__"


class VendorOrderProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = m.VendorOrderProduct
        fields = "__all__"


class VendorOrderSerializer(serializers.ModelSerializer):
    products = VendorOrderProductSerializer(many=True, source="orderproduct_set")

    class Meta:
        model = m.VendorOrder
        exclude = ("order",)


class OrderSerializer(serializers.ModelSerializer):
    vendor_orders = VendorOrderSerializer(many=True)

    class Meta:
        model = m.Order
        fields = "__all__"


class OrderListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    order_date = serializers.DateField()
    status = serializers.CharField()
    total_items = serializers.CharField()


class OfficeVendorConnectedSerializer(serializers.Serializer):
    office_associated_id = serializers.CharField()
    id = serializers.CharField()
    name = serializers.CharField()


class TotalSpendSerializer(serializers.Serializer):
    vendor = OfficeVendorConnectedSerializer(read_only=True)
    month = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartProductSerializer(serializers.ModelSerializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=m.Vendor.objects.all())

    class Meta:
        model = m.CartProduct
        fields = "__all__"

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["vendor"] = VendorSerializer(m.Vendor.objects.get(id=ret["vendor"])).data
        return ret


class CartSerializer(serializers.ModelSerializer):
    product = CartProductSerializer()
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())

    class Meta:
        model = m.Cart
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            cart_product = m.CartProduct.objects.create(**validated_data.pop("product"))
            return m.Cart.objects.create(product=cart_product, **validated_data)
