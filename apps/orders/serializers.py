from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework_recursive.fields import RecursiveField

from apps.accounts.serializers import VendorSerializer
from apps.orders.helpers import OfficeProductHelper, OfficeVendorHelper, ProductHelper

from . import models as m


class OfficeProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OfficeProductCategory
        exclude = ("created_at", "updated_at")
        extra_kwargs = {"slug": {"read_only": True}}

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if self.context.get("with_inventory_count"):
            office_inventory_products = instance.products.filter(is_inventory=True)
            ret["vendor_ids"] = set(office_inventory_products.values_list("product__vendor__id", flat=True))
            ret["count"] = office_inventory_products.count()

        return ret


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ProductCategory
        fields = (
            "id",
            "name",
            "slug",
        )


class OfficeReadSerializer(serializers.Serializer):
    office_id = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ProductImage
        fields = ("image",)


class SimpleProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, required=False)
    is_inventory = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = m.Product
        fields = (
            "id",
            "name",
            "images",
            "is_inventory",
        )


class ProductV2Serializer(serializers.ModelSerializer):
    vendor = VendorSerializer()
    category = ProductCategorySerializer()
    images = ProductImageSerializer(many=True, required=False)
    product_price = serializers.DecimalField(decimal_places=2, max_digits=10, read_only=True)
    is_inventory = serializers.BooleanField(default=False, read_only=True)
    last_order_date = serializers.DateField(required=False)

    class Meta:
        model = m.Product
        fields = (
            "id",
            "vendor",
            "name",
            "product_id",
            "category",
            "product_unit",
            "url",
            "product_price",
            "images",
            "is_inventory",
            "last_order_date",
        )
        ordering = ("name",)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        office_pk = self.context.get("office_pk")
        children_ids = instance.children.values_list("id", flat=True)
        if children_ids:
            children_products = ProductHelper.get_products(
                office=office_pk, fetch_parents=False, product_ids=children_ids
            )
            ret["children"] = self.__class__(children_products, many=True).data
        else:
            ret["children"] = []

        return ret


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
    status_display_text = serializers.CharField(source="get_status_display")

    class Meta:
        model = m.VendorOrderProduct
        fields = "__all__"

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        if instance.status == m.VendorOrderProduct.Status.RECEIVED:
            vendor_order = instance.vendor_order
            order = vendor_order.order

            if not m.VendorOrderProduct.objects.filter(
                Q(vendor_order=vendor_order), ~Q(status=m.VendorOrderProduct.Status.RECEIVED)
            ).exists():
                instance.vendor_order.status = m.OrderStatus.COMPLETE
                instance.vendor_order.save()

            if not m.VendorOrderProduct.objects.filter(
                Q(vendor_order__order=order), ~Q(status=m.VendorOrderProduct.Status.RECEIVED)
            ).exists():
                order.status = m.OrderStatus.COMPLETE
                order.save()

        return instance


class VendorOrderSerializer(serializers.ModelSerializer):
    products = VendorOrderProductSerializer(many=True, source="order_products")
    vendor = VendorSerializer()
    status_display_text = serializers.CharField(source="get_status_display")

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
    description = serializers.CharField(allow_null=True, allow_blank=True)
    url = serializers.CharField()


class OfficeProductReadSerializer(serializers.Serializer):
    product = ProductDataSerializer()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Cart
        fields = "__all__"

    def create(self, validated_data):
        validated_data["unit_price"] = OfficeProductHelper.get_product_price(
            office=validated_data["office"], product=validated_data["product"]
        )
        return super().create(validated_data)


class CartSerializer(serializers.ModelSerializer):
    # office_product = OfficeProductReadSerializer(write_only=True)
    product = ProductSerializer(read_only=True, required=False)
    # same_products = serializers.SerializerMethodField()
    # office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())

    class Meta:
        model = m.Cart
        fields = "__all__"

    # def validate(self, attrs):
    #     if not self.instance:
    #         product_id = attrs["office_product"]["product"]["product_id"]
    #         office = attrs["office"]
    #         if m.Cart.objects.filter(office=office, product__product_id=product_id).exists():
    #             raise serializers.ValidationError({"message": "This product is already in your cart"})
    #     return attrs

    # def create(self, validated_data):
    #     with transaction.atomic():
    #         office_product = validated_data.pop("office_product", {})
    #         product_data = office_product.pop("product")
    #         office = validated_data.get("office")
    #         vendor = product_data.pop("vendor")
    #         product_id = product_data.pop("product_id")
    #         images = product_data.pop("images", [])
    #         product, created = m.Product.objects.get_or_create(
    #             vendor=vendor, product_id=product_id, defaults=product_data
    #         )
    #         if created:
    #             product_images_objs = []
    #             for image in images:
    #                 product_images_objs.append(m.ProductImage(product=product, image=image["image"]))
    #             if images:
    #                 m.ProductImage.objects.bulk_create(product_images_objs)

    #         try:
    #             price = office_product.pop("price")
    #             m.OfficeProduct.objects.update_or_create(office=office, product=product, defaults={"price": price})
    #             return m.Cart.objects.create(product=product, **validated_data)
    #         except IntegrityError:
    #             raise serializers.ValidationError({"message": "This product is already in your cart"})

    def to_representation(self, instance):
        # TODO: return sibling products from linked vendor
        ret = super().to_representation(instance)
        connected_vendor_ids = OfficeVendorHelper.get_connected_vendor_ids(office=instance.office)
        ret["sibling_products"] = ProductSerializer(
            instance.product.sibling_products.filter(vendor_id__in=connected_vendor_ids),
            many=True,
        ).data
        return ret


class OfficeCheckoutStatusUpdateSerializer(serializers.Serializer):
    checkout_status = serializers.ChoiceField(choices=m.OfficeCheckoutStatus.CHECKOUT_STATUS.choices)


class OfficeProductSerializer(serializers.ModelSerializer):
    product_data = ProductSerializer(write_only=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), write_only=True)
    product = ProductV2Serializer(read_only=True)
    office_product_category = serializers.PrimaryKeyRelatedField(queryset=m.OfficeProductCategory.objects.all())

    class Meta:
        model = m.OfficeProduct
        fields = (
            "id",
            "office",
            "product",
            "product_data",
            "price",
            "office_product_category",
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
        ret["office_product_category"] = OfficeProductCategorySerializer(instance.office_product_category).data
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


class ProductSuggestionSerializer(serializers.Serializer):
    id = serializers.CharField()
    product_id = serializers.CharField()
    name = serializers.CharField()
    image = serializers.CharField()
    is_inventory = serializers.BooleanField()


class RejectProductSerializer(serializers.Serializer):
    order_product_id = serializers.CharField()
    rejected_reason = serializers.ChoiceField(choices=m.VendorOrderProduct.RejectReason.choices)


class ApproveRejectSerializer(serializers.Serializer):
    is_approved = serializers.BooleanField()
    rejected_items = serializers.ListSerializer(child=RejectProductSerializer(), required=False)
    rejected_reason = serializers.CharField(required=False)


class VendorProductSearchPagination(serializers.Serializer):
    vendor = serializers.CharField()
    page = serializers.IntegerField()


class VendorProductSearchSerializer(serializers.Serializer):
    q = serializers.CharField()
    max_price = serializers.IntegerField(allow_null=True, min_value=0)
    min_price = serializers.IntegerField(allow_null=True, min_value=0)
    vendors = VendorProductSearchPagination(many=True)


class ProductPriceRequestSerializer(serializers.Serializer):
    products = serializers.PrimaryKeyRelatedField(queryset=m.Product.objects.all(), many=True)
