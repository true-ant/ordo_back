from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Office, Card, Subscription
from apps.accounts.services.stripe import get_payment_method_token, add_customer_to_stripe, create_subscription


def update_subscription(user, office: Office, data: dict):

    card_number = data.get("cc_number")
    expiry = data.get("cc_expiry")
    cvc = data.get("cc_code")
    coupon = data.get("coupon")

    if not card_number and not expiry and not cvc:
        return

    card_token = get_payment_method_token(card_number=card_number, expiry=expiry, cvc=cvc)
    if office.cards.filter(card_token=card_token.id).exists():
        return

    _, customer = add_customer_to_stripe(
        email=user.email,
        customer_name=office.name,
        payment_method_token=card_token,
    )

    subscription = create_subscription(customer_id=customer.id, promocode=coupon)

    with transaction.atomic():
        Card.objects.create(
            last4=card_token.card.last4,
            customer_id=customer.id,
            card_token=card_token.id,
            office=office,
        )
        Subscription.objects.create(
            subscription_id=subscription.id, office=office, start_on=timezone.now().date()
        )