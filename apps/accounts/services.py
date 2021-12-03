from typing import Tuple

from django.utils import timezone

from apps.common import messages as msgs

from .models import Office, Subscription
from .stripe import cancel_subscription as stripe_cancel_subscription
from .stripe import create_subscription as stripe_create_subscription


def cancel_subscription(office: Office) -> Tuple[bool, str]:
    active_subscription = office.subscriptions.filter(cancelled_on__isnull=True).order_by("-updated_at").first()
    if active_subscription is None:
        return False, msgs.OFFICE_HAS_NO_SUBSCRIPTION
    try:
        stripe_cancel_subscription(active_subscription.subscription_id)
    except Exception as e:
        return False, f"{e}"
    else:
        active_subscription.cancelled_on = timezone.now()
        active_subscription.save()
        return True, "Subscription cancelled successfully"


def create_subscription(office: Office) -> Tuple[bool, str]:
    active_subscription = office.subscriptions.filter(cancelled_on__isnull=True).order_by("-updated_at").first()
    if active_subscription:
        return False, msgs.OFFICE_HAS_ACTIVE_SUBSCRIPTION
    try:
        subscription = stripe_create_subscription(office.card.customer_id)
    except Exception as e:
        return False, f"{e}"
    else:
        Subscription.objects.create(subscription_id=subscription.id, start_on=timezone.now(), office=office)
        return True, "Subscription renewed successfully"
