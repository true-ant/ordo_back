from rest_framework import serializers
from rest_framework_recursive.fields import RecursiveField

from apps.accounts.models import User
from apps.audit.models import ProductRelationHistory
from apps.orders.models import Product


class AuditProductSerializer(serializers.ModelSerializer):
    children = serializers.ListSerializer(child=RecursiveField())

    class Meta:
        model = Product
        fields = "__all__"


def unlink_from_parent(p: Product, user: User):
    parent = p.parent
    before_json = AuditProductSerializer(instance=parent).data
    p.parent_id = None
    p.save(update_fields=["parent_id"])
    parent.refresh_from_db()
    after_json = AuditProductSerializer(instance=parent).data
    ProductRelationHistory.objects.create(before=before_json, after=after_json, user=user)


def attach_to_parent(p: Product, new_parent: Product, user: User):
    before_json = AuditProductSerializer(instance=new_parent).data
    p.parent_id = new_parent.pk
    p.save(update_fields=["parent_id"])
    new_parent.refresh_from_db()
    after_json = AuditProductSerializer(instance=new_parent).data
    ProductRelationHistory.objects.create(before=before_json, after=after_json, user=user)
