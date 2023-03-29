from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver

from apps.orders.models import (
    OfficeVendorShippingOptions as OfficeVendorShippingOptionsModel,
)
from apps.orders.models import ShippingMethod as ShippingMethodModel


def remove_shipping_methods(shipping_methods_pks):
    unreferenced = ShippingMethodModel.objects.filter(pk__in=shipping_methods_pks)
    unreferenced.delete()


@receiver(m2m_changed, sender=OfficeVendorShippingOptionsModel.shipping_options.through)
def handle_tags(sender, **kwargs):
    action = kwargs["action"]
    if action == "pre_clear":
        shipping_methods_pks = kwargs["instance"].shipping_options.values_list("pk")
    elif action == "pre_remove":
        shipping_methods_pks = kwargs.get("pk_set")
    else:
        return
    remove_shipping_methods(shipping_methods_pks)


@receiver(pre_delete, sender=OfficeVendorShippingOptionsModel)
def handle_shipping_options(sender, **kwargs):
    shipping_methods_pks = kwargs["instance"].shipping_options.values_list("pk")
    remove_shipping_methods(shipping_methods_pks)
