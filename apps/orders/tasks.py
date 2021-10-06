import datetime

from celery import shared_task
from django.utils import timezone

from apps.orders.models import OrderProgressStatus


@shared_task
def update_checkout_status():
    ten_minutes_ago = timezone.now() - datetime.timedelta(minutes=10)
    objs = OrderProgressStatus.objects.filter(
        status=OrderProgressStatus.STATUS.IN_PROGRESS, updated_at__lt=ten_minutes_ago
    )
    total_count = objs.count()
    batch_size = 100
    for i in range(0, total_count, batch_size):
        batch_objs = objs[i * batch_size : min((i + 1) * batch_size, total_count)]
        for obj in batch_objs:
            obj.status = OrderProgressStatus.STATUS.COMPLETE
        OrderProgressStatus.objects.bulk_update(batch_objs, ["status"])
