from django.db import transaction
from rest_framework import serializers

from apps.accounts.serializers import VendorSerializer

from . import models as m


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ProductImage
        fields = ("image",)


class ProductSerializer(serializers.ModelSerializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=m.Vendor.objects.all())
    images = ProductImageSerializer(many=True)

    class Meta:
        model = m.Product
        fields = "__all__"

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["vendor"] = VendorSerializer(m.Vendor.objects.get(id=ret["vendor"])).data
        return ret


class VendorOrderProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = m.VendorOrderProduct
        fields = "__all__"


class VendorOrderSerializer(serializers.ModelSerializer):
    products = VendorOrderProductSerializer(many=True, source="vendororderproduct_set")

    class Meta:
        model = m.VendorOrder
        exclude = ("order",)


class OrderSerializer(serializers.ModelSerializer):
    vendor_orders = VendorOrderSerializer(many=True)

    class Meta:
        model = m.Order
        fields = "__all__"


class OrderListSerializer(serializers.ModelSerializer):
    vendors = serializers.SerializerMethodField()

    class Meta:
        model = m.Order
        fields = (
            "id",
            "vendors",
            "total_amount",
            "order_date",
            "status",
            "total_items",
        )

    def get_vendors(self, instance):
        vendors = instance.vendor_orders.select_related("vendor")
        return VendorSerializer([vendor.vendor for vendor in vendors], many=True).data


class OfficeVendorConnectedSerializer(serializers.Serializer):
    office_associated_id = serializers.CharField()
    id = serializers.CharField()
    name = serializers.CharField()
    logo = serializers.CharField()


class TotalSpendSerializer(serializers.Serializer):
    vendor = OfficeVendorConnectedSerializer(read_only=True)
    month = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())

    class Meta:
        model = m.Cart
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            product_data = validated_data.pop("product")
            vendor = product_data.pop("vendor")
            product_id = product_data.pop("product_id")
            try:
                product = m.Product.objects.get(vendor=vendor, product_id=product_id)
                for k, v in product_data.items():
                    setattr(product, k, v)
                product.save()
            except m.Product.DoesNotExist:
                images = product_data.pop("images", [])
                product = m.Product.objects.create(vendor=vendor, product_id=product_id, **product_data)
                product_images_objs = []
                for image in images:
                    product_images_objs.append(m.ProductImage(product=product, image=image))
                if images:
                    m.ProductImage.objects.bulk_create(product_images_objs)

            return m.Cart.objects.create(product=product, **validated_data)
