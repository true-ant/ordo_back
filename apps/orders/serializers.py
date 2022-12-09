from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework_recursive.fields import RecursiveField

from apps.accounts.helper import OfficeBudgetHelper
from apps.accounts.serializers import VendorLiteSerializer
from apps.common.choices import OrderStatus
from apps.common.serializers import Base64ImageField
from apps.orders.helpers import OfficeProductHelper, ProductHelper

from . import models as m


class OfficeProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OfficeProductCategory
        exclude = ("created_at", "updated_at")
        extra_kwargs = {"slug": {"read_only": True}}

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if self.context.get("with_inventory_count"):
            office_inventory_products = instance.products.filter(is_inventory=True).exclude(
                product__vendor__isnull=True
            )
            ret["vendor_ids"] = set(office_inventory_products.values_list("product__vendor__id", flat=True))
            ret["count"] = office_inventory_products.count()

        return ret

class OfficeProductVendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Vendor
        fields = "__all__"

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if self.context.get("with_inventory_count"):
            
            office_inventory_products = m.OfficeProduct.objects.all().filter(
                office_id=self.context["office_id"],
                product__vendor_id=instance.id,
                is_inventory=True).exclude(
                product__vendor__isnull=True
            )
            ret["category_ids"] = set(office_inventory_products.values_list("office_product_category_id", flat=True))
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
    image = serializers.SerializerMethodField()
    is_inventory = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = m.Product
        fields = (
            "id",
            "name",
            "image",
            "is_inventory",
        )

    def get_image(self, instance):
        if instance.vendor is None:
            image = m.ProductImage.objects.filter(product__parent=instance).first()
        else:
            image = instance.images.first()
        if image:
            return image.image


class ProductV2Serializer(serializers.ModelSerializer):
    vendor = VendorLiteSerializer()
    category = ProductCategorySerializer()
    images = ProductImageSerializer(many=True, required=False)
    product_price = serializers.DecimalField(decimal_places=2, max_digits=10, read_only=True)
    is_inventory = serializers.BooleanField(default=False, read_only=True)
    product_vendor_status = serializers.CharField(read_only=True)
    last_order_date = serializers.DateField(read_only=True)
    nickname = serializers.CharField(max_length=128, allow_null=True)
    # image_url = Base64ImageField()

    last_order_price = serializers.DecimalField(decimal_places=2, max_digits=10, read_only=True)

    class Meta:
        model = m.Product
        fields = (
            "id",
            "vendor",
            "name",
            "nickname",
            # "image_url",
            "product_id",
            "manufacturer_number",
            "category",
            "product_unit",
            "url",
            "images",
            "product_price",
            "is_special_offer",
            "special_price",
            "promotion_description",
            "is_inventory",
            "product_vendor_status",
            "last_order_date",
            "last_order_price",
        )
        ordering = ("name",)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        office_pk = self.context.get("office_pk")
        # if you want to filter out pricing comparision products, uncomment it
        # vendors = self.context.get("vendors")
        if hasattr(instance, "office_product") and instance.office_product:
            ret["product_vendor_status"] = instance.office_product[0].product_vendor_status
            ret["last_order_date"] = instance.office_product[0].last_order_date
            ret["last_order_price"] = instance.office_product[0].last_order_price
            ret["nickname"] = instance.office_product[0].nickname
            # ret["image_url"] = instance.office_product[0].image_url

        if instance.vendor and instance.vendor.slug in settings.NON_FORMULA_VENDORS:
            ret["product_price"] = instance.recent_price

        # if hasattr(instance, "office_product") and instance.office_product:
        #     if "product_price" not in ret:
        #         ret["product_price"] = instance.office_product[0].recent_price

        children_ids = instance.children.values_list("id", flat=True)
        # if you want to filter out pricing comparision products, uncomment it
        # if vendors:
        #     children_ids = children_ids.filter(vendor__slug__in=vendors)

        if children_ids:
            children_products = ProductHelper.get_products(
                office=office_pk, fetch_parents=False, product_ids=children_ids
            )
            ret["children"] = self.__class__(children_products, many=True, context={"office_pk": office_pk}).data
            last_order_dates = sorted(
                [
                    (child["last_order_date"], child["last_order_price"])
                    for child in ret["children"]
                    if child["is_inventory"]
                ],
                key=lambda x: x[0],
                reverse=True,
            )
            if last_order_dates:
                ret["last_order_date"] = last_order_dates[0][0]
                ret["last_order_price"] = last_order_dates[0][1]
        else:
            ret["children"] = []

        if instance.parent is None:
            ret["description"] = instance.description
        return ret


class PromoSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Promotion
        fields = "__all__"

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
            "is_special_offer",
            "description",
            "url",
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if ret["vendor"]:
            ret["vendor"] = VendorLiteSerializer(m.Vendor.objects.get(id=ret["vendor"])).data
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
        with transaction.atomic():
            OfficeBudgetHelper.move_spend_category(
                office=instance.vendor_order.order.office,
                date=instance.vendor_order.order.order_date,
                amount=instance.unit_price * instance.quantity,
                from_category=instance.budget_spend_type,
                to_category=validated_data.get("budget_spend_type"),
            )

            instance = super().update(instance, validated_data)

            if instance.status == m.ProductStatus.RECEIVED:
                vendor_order = instance.vendor_order
                order = vendor_order.order

                if not m.VendorOrderProduct.objects.filter(
                    Q(vendor_order=vendor_order), ~Q(status=m.ProductStatus.RECEIVED)
                ).exists():
                    instance.vendor_order.status = OrderStatus.CLOSED
                    instance.vendor_order.save()

                if not m.VendorOrderProduct.objects.filter(
                    Q(vendor_order__order=order), ~Q(status=m.ProductStatus.RECEIVED)
                ).exists():
                    order.status = OrderStatus.CLOSED
                    order.save()

            return instance


class VendorOrderSerializer(serializers.ModelSerializer):
    products = VendorOrderProductSerializer(many=True, source="order_products")
    vendor = VendorLiteSerializer()
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
        return VendorLiteSerializer([vendor.vendor for vendor in vendors], many=True).data


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
    promo = PromoSerializer(read_only=True,required=False)
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
        sibling_products = OfficeProductHelper.get_available_sibling_products(
            office=instance.office, product=instance.product
        )
        ret["sibling_products"] = ProductV2Serializer(
            sibling_products,
            many=True,
        ).data
        return ret


class OfficeCheckoutStatusUpdateSerializer(serializers.Serializer):
    checkout_status = serializers.ChoiceField(choices=m.OfficeCheckoutStatus.CHECKOUT_STATUS.choices)


class OfficeProductSerializer(serializers.ModelSerializer):
    product_data = ProductSerializer(write_only=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), write_only=True)
    office_product_category = serializers.PrimaryKeyRelatedField(queryset=m.OfficeProductCategory.objects.all())
    vendor = serializers.CharField(read_only=True)
    image_url = Base64ImageField()

    class Meta:
        model = m.OfficeProduct
        fields = (
            "id",
            "office",
            "product_data",
            "price",
            "office_product_category",
            "is_favorite",
            "is_inventory",
            "nickname",
            "image_url",
            "last_order_date",
            "last_order_price",
            "vendor",
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
        
        if "nickname" in self.initial_data:
            office_product = m.OfficeProduct.objects.filter(
                office=instance.office, product_id=instance.product_id
            )
            office_product.nickname = self.initial_data["nickname"]
            m.OfficeProduct.objects.bulk_update(office_product, ["nickname"])

        # if "image_url" in self.initial_data:
        #     office_product = m.OfficeProduct.objects.filter(
        #         office=instance.office, product_id=instance.product_id
        #     )
        #     office_product.image_url = self.initial_data['image_url']
        #     m.OfficeProduct.objects.bulk_update(office_product, ["image_url"])

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
        ret["product"] = ProductV2Serializer(instance.product, context=self.context).data

        if ret["is_inventory"]:
            if ret["product"]["vendor"]:
                ret["vendor"] = ret["product"]["vendor"]["slug"]
            else:
                last_order_products = sorted(
                    [
                        (child["last_order_date"], child["last_order_price"], child["vendor"]["slug"], child["id"])
                        for child in ret["product"]["children"]
                        if child["is_inventory"] is True
                    ],
                    key=lambda x: x[0],
                    reverse=True,
                )
                if last_order_products:
                    ret["last_order_date"] = last_order_products[0][0]
                    ret["last_order_price"] = last_order_products[0][1]
                    ret["vendor"] = last_order_products[0][2]
                    # this is a little complicated
                    ret["product"]["id"] = last_order_products[0][3]
                else:
                    ret["last_order_date"] = None
                    ret["last_order_price"] = None
                    ret["vendor"] = None

            # children_products = ret["product"].get("children", [])
        # if children_products:
        #     children_product_ids = [child["id"] for child in children_products]
        #     q = Q(office=instance.office) & Q(product_id__in=children_product_ids)
        #     if self.context.get("filter_inventory", False):
        #         q &= Q(is_inventory=True)
        #
        #     office_products = m.OfficeProduct.objects.filter(q)
        #     office_products = {office_product.product.id: office_product for office_product in office_products}
        #     ret["product"]["children"] = [
        #         {
        #             "product": child_product,
        #             "price": office_products[child_product["id"]].price,
        #         }
        #         for child_product in children_products
        #         if child_product["id"] in office_products
        #     ]

        # if ret["is_inventory"]:
        #     last_order = (
        #         m.VendorOrderProduct.objects.select_related("vendor_order")
        #         .filter(product__product_id=ret["product"]["product_id"])
        #         .order_by("-vendor_order__order_date")
        #         .first()
        #     )
        #     if last_order:
        #         ret["last_order_date"] = last_order.vendor_order.order_date.isoformat()
        #         ret["last_order_price"] = last_order.unit_price
        #     else:
        #         ret["last_order_date"] = None
        #         ret["last_order_price"] = None
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

class VendorOrderReturnSerializer(serializers.Serializer):
    return_items = serializers.ListSerializer(child=serializers.CharField())
    email_list = serializers.ListSerializer(child=serializers.CharField(), required=False)
