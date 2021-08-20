from collections import defaultdict
from typing import List

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.accounts.models import Office
from apps.types.accounts import OfficeInvite

UserModel = get_user_model()


@shared_task
def send_forgot_password_mail(user_id, token):
    user = UserModel.objects.get(pk=user_id)
    htm_content = render_to_string(
        "emails/reset_password.html",
        {
            "USER": user,
            "SECRET": token,
            "SITE_URL": settings.SITE_URL,
        },
    )
    send_mail(
        subject="Reset your Ordo password",
        message="message",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=htm_content,
    )


@shared_task
def send_office_invite_email(office_email_invites: List[OfficeInvite]):
    office_invites = defaultdict(list)

    for invite in office_email_invites:
        office_invites[invite["office_id"]].append(invite["email"])

    Office.objects.in_bulk(id_list=list(office_invites.keys()))

    for office_id, emails in office_invites.items():
        htm_content = render_to_string(
            "emails/invite.html",
            {
                "SITE_URL": settings.SITE_URL,
            },
        )
        send_mail(
            subject="You've been invited!",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            html_message=htm_content,
        )
