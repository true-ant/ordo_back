import asyncio
from collections import defaultdict
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string

from apps.accounts.models import Office, OfficeVendor
from apps.orders.models import Order, OrderProduct, Product
from apps.scrapers.scraper_factory import ScraperFactory
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


async def get_orders(office_vendor, login_cookies):
    async with ClientSession(cookies=login_cookies) as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name=office_vendor.vendor.slug,
            session=session,
        )
        return await scraper.get_orders()


@shared_task
def fetch_orders_from_vendor(office_vendor_id, login_cookies):
    cookie = SimpleCookie()
    for login_cookie in login_cookies.split("\r\n"):
        login_cookie = login_cookie.replace("Set-Cookie: ", "")
        cookie.load(login_cookie)
    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    orders = asyncio.run(get_orders(office_vendor, cookie))
    with transaction.atomic():
        for order_data_cls in orders:
            order_data = order_data_cls.to_dict()
            order_products_data = order_data.pop("products")
            order = Order.from_dataclass(office_vendor, order_data)
            for order_product_data in order_products_data:
                product = Product.from_dataclass(office_vendor.vendor, order_product_data["product"])
                OrderProduct.objects.create(
                    order=order,
                    product=product,
                    quantity=order_product_data["quantity"],
                    unit_price=order_product_data["unit_price"],
                    status=order_product_data["status"],
                )
