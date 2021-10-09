import datetime

from celery import shared_task
from django.utils import timezone

from apps.orders.models import OfficeCheckoutStatus


@shared_task
def update_office_cart_status():
    ten_minutes_ago = timezone.now() - datetime.timedelta(minutes=10)
    objs = OfficeCheckoutStatus.objects.filter(
        checkout_status=OfficeCheckoutStatus.CHECKOUT_STATUS.IN_PROGRESS,
        order_status=OfficeCheckoutStatus.ORDER_STATUS.COMPLETE,
        updated_at__lt=ten_minutes_ago,
    )
    total_count = objs.count()
    batch_size = 100
    for i in range(0, total_count, batch_size):
        batch_objs = objs[i * batch_size : min((i + 1) * batch_size, total_count)]
        for obj in batch_objs:
            obj.checkout_status = OfficeCheckoutStatus.CHECKOUT_STATUS.COMPLETE
        OfficeCheckoutStatus.objects.bulk_update(batch_objs, ["checkout_status"])
