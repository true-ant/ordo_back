from django.db import transaction
from django.db.utils import IntegrityError
from rest_framework import serializers
from rest_framework_recursive.fields import RecursiveField

from apps.accounts.serializers import VendorSerializer

from . import models as m


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ProductCategory
        fields = (
            "id",
            "name",
            "slug",
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        office = self.context.get("office")
        vendors = self.context.get("vendors")
        if office:
            office_inventory_products_queryset = m.OfficeProduct.objects.filter(
                is_inventory=True,
                office=office,
                office_category=instance,
            )
            vendor_ids = set(office_inventory_products_queryset.values_list("product__vendor__id", flat=True))
            ret["vendors"] = [vendor.to_dict() for vendor in vendors if vendor.id in vendor_ids]
            ret["count"] = office_inventory_products_queryset.count()
        return ret


class OfficeReadSerializer(serializers.Serializer):
    office_id = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ProductImage
        fields = ("image",)


class ProductSerializer(serializers.ModelSerializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=m.Vendor.objects.all())
    images = ProductImageSerializer(many=True, required=False)
    category = ProductCategorySerializer(read_only=True)
    children = serializers.ListSerializer(child=RecursiveField())

    class Meta:
        model = m.Product
        fields = (
            "id",
            "vendor",
            "images",
            "category",
            "children",
            "product_id",
            "name",
            "product_unit",
            "description",
            "url",
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["vendor"] = VendorSerializer(m.Vendor.objects.get(id=ret["vendor"])).data
        return ret


class ProductReadDetailSerializer(serializers.Serializer):
    office_id = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())
    vendor = serializers.PrimaryKeyRelatedField(queryset=m.Vendor.objects.all())
    product_id = serializers.CharField()
    product_url = serializers.URLField()


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

    def validate(self, attrs):
        if not self.instance:
            product_id = attrs["product"]["product_id"]
            office = attrs["office"]
            if m.Cart.objects.filter(office=office, product__product_id=product_id).exists():
                raise serializers.ValidationError({"message": "This product is already in your cart"})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            product_data = validated_data.pop("product")
            vendor = product_data.pop("vendor")
            product_id = product_data.pop("product_id")
            images = product_data.pop("images", [])
            product, created = m.Product.objects.get_or_create(
                vendor=vendor, product_id=product_id, defaults=product_data
            )
            if created:
                product_images_objs = []
                for image in images:
                    product_images_objs.append(m.ProductImage(product=product, image=image["image"]))
                if images:
                    m.ProductImage.objects.bulk_create(product_images_objs)

            try:
                return m.Cart.objects.create(product=product, **validated_data)
            except IntegrityError:
                raise serializers.ValidationError({"message": "This product is already in your cart"})


class OfficeCheckoutStatusUpdateSerializer(serializers.Serializer):
    checkout_status = serializers.ChoiceField(choices=m.OfficeCheckoutStatus.CHECKOUT_STATUS.choices)


class OfficeProductSerializer(serializers.ModelSerializer):
    product_data = ProductSerializer(write_only=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), write_only=True)
    product = ProductSerializer(read_only=True)
    office_category = serializers.PrimaryKeyRelatedField(queryset=m.ProductCategory.objects.all())

    class Meta:
        model = m.OfficeProduct
        fields = (
            "id",
            "office",
            "product",
            "product_data",
            "price",
            "office_category",
            "is_favorite",
            "is_inventory",
        )

    def create(self, validated_data):
        with transaction.atomic():
            product_data = validated_data.pop("product_data")
            vendor = product_data.pop("vendor")
            product_id = product_data.pop("product_id")
            images = product_data.pop("images", [])
            product, created = m.Product.objects.get_or_create(
                vendor=vendor, product_id=product_id, defaults=product_data
            )

            if created:
                product_images_objs = []
                for image in images:
                    product_images_objs.append(m.ProductImage(product=product, image=image))
                if images:
                    m.ProductImage.objects.bulk_create(product_images_objs)

            return m.OfficeProduct.objects.create(product=product, **validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["office_category"] = ProductCategorySerializer(instance.office_category).data
        return ret


class ClearCartSerializer(serializers.Serializer):
    remove = serializers.ChoiceField(choices=["save_for_later", "cart"])
