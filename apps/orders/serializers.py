from django.db import transaction
from django.db.models import Q
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
    children = serializers.ListSerializer(child=RecursiveField(), required=False, read_only=True)

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
        if not self.context.get("include_children", False):
            ret.pop("children", None)

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
    vendor = VendorSerializer()

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


class ProductDataSerializer(serializers.Serializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=m.Vendor.objects.all())
    images = ProductImageSerializer(many=True, required=False)
    product_id = serializers.CharField()
    category = serializers.PrimaryKeyRelatedField(
        queryset=m.ProductCategory.objects.all(), allow_null=True, allow_empty=True
    )
    name = serializers.CharField()
    product_unit = serializers.CharField(allow_null=True, allow_blank=True)
    description = serializers.CharField()
    url = serializers.CharField()


class OfficeProductReadSerializer(serializers.Serializer):
    product = ProductDataSerializer()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartSerializer(serializers.ModelSerializer):
    office_product = OfficeProductReadSerializer(write_only=True)
    product = ProductSerializer(read_only=True, required=False)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())

    class Meta:
        model = m.Cart
        fields = "__all__"

    def validate(self, attrs):
        if not self.instance:
            product_id = attrs["office_product"]["product"]["product_id"]
            office = attrs["office"]
            if m.Cart.objects.filter(office=office, product__product_id=product_id).exists():
                raise serializers.ValidationError({"message": "This product is already in your cart"})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            office_product = validated_data.pop("office_product", {})
            product_data = office_product.pop("product")
            office = validated_data.get("office")
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
                price = office_product.pop("price")
                m.OfficeProduct.objects.update_or_create(office=office, product=product, defaults={"price": price})
                return m.Cart.objects.create(product=product, **validated_data)
            except IntegrityError:
                raise serializers.ValidationError({"message": "This product is already in your cart"})

    def to_representation(self, instance):
        ret = super(CartSerializer, self).to_representation(instance)
        # ret["product"].pop("children")
        return ret


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

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        children_product_ids = [child.id for child in instance.product.children.all()]
        if children_product_ids:
            office_products = m.OfficeProduct.objects.filter(
                office=instance.office, product_id__in=children_product_ids
            )

            # TODO: code optimization
            if "is_favorite" in validated_data:
                for office_product in office_products:
                    office_product.is_favorite = validated_data["is_favorite"]
                m.OfficeProduct.objects.bulk_update(office_products, ["is_favorite"])

            if "is_inventory" in validated_data:
                for office_product in office_products:
                    office_product.is_favorite = validated_data["is_inventory"]
                m.OfficeProduct.objects.bulk_update(office_products, ["is_inventory"])

        return instance

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["office_category"] = ProductCategorySerializer(instance.office_category).data
        children_products = ret["product"].get("children", [])
        if children_products:
            children_product_ids = [child["id"] for child in children_products]
            q = Q(office=instance.office) & Q(product_id__in=children_product_ids)
            if self.context.get("filter_inventory", False):
                q &= Q(is_inventory=True)

            office_products = m.OfficeProduct.objects.filter(q)
            office_products = {office_product.product.id: office_product for office_product in office_products}
            ret["product"]["children"] = [
                {
                    "product": child_product,
                    "price": office_products[child_product["id"]].price,
                }
                for child_product in children_products
                if child_product["id"] in office_products
            ]

        if ret["is_inventory"]:
            last_order = (
                m.VendorOrderProduct.objects.select_related("vendor_order")
                .filter(product__product_id=ret["product"]["product_id"])
                .order_by("-vendor_order__order_date")
                .first()
            )
            if last_order:
                ret["last_order_date"] = last_order.vendor_order.order_date.isoformat()
                ret["last_order_price"] = last_order.unit_price
            else:
                ret["last_order_date"] = None
                ret["last_order_price"] = None
        return ret


class ClearCartSerializer(serializers.Serializer):
    remove = serializers.ChoiceField(choices=["save_for_later", "cart"])


class ProductSuggestionSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = m.Product
        fields = ("id", "product_id", "name", "image")

    def get_image(self, instance):
        image = instance.images.first()
        return image.image if image else ""
