import asyncio
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string

from apps.accounts.models import CompanyVendor
from apps.orders.models import Order, OrderProduct, Product
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.accounts import CompanyInvite

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
def send_company_invite_email(company_email_invites: List[CompanyInvite]):
    # company_invites = defaultdict(list)
    #
    # for invite in office_email_invites:
    #     office_invites[invite["office_id"]].append(invite["email"])
    #
    # Office.objects.in_bulk(id_list=list(office_invites.keys()))
    #
    # for office_id, emails in office_invites.items():
    emails = [invite["email"] for invite in company_email_invites]
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


async def get_orders(company_vendor, login_cookies, perform_login):
    async with ClientSession(cookies=login_cookies) as session:
        scraper = ScraperFactory.create_scraper(
            scraper_name=company_vendor.vendor.slug,
            session=session,
            username=company_vendor.username,
            password=company_vendor.password,
        )
        return await scraper.get_orders(perform_login=perform_login)


@shared_task
def fetch_orders_from_vendor(company_vendor_id, login_cookies=None, perform_login=False):
    if login_cookies is None and perform_login is False:
        return

    company_vendor = CompanyVendor.objects.select_related("company", "vendor").get(id=company_vendor_id)
    offices = company_vendor.company.offices.all()

    if login_cookies:
        cookie = SimpleCookie()
        for login_cookie in login_cookies.split("\r\n"):
            login_cookie = login_cookie.replace("Set-Cookie: ", "")
            cookie.load(login_cookie)
    else:
        cookie = None
    orders = asyncio.run(get_orders(company_vendor, cookie, perform_login))

    with transaction.atomic():
        for order_data_cls in orders:
            order_data = order_data_cls.to_dict()
            order_products_data = order_data.pop("products")
            shipping_address = order_data.pop("shipping_address")
            try:
                office = [
                    office for office in offices if office.postal_code[:5] == shipping_address["postal_code"][:5]
                ][0]
            except (TypeError, IndexError):
                office = offices[0]

            order = Order.from_dataclass(vendor=company_vendor.vendor, office=office, dict_data=order_data)
            for order_product_data in order_products_data:
                product = Product.from_dataclass(company_vendor.vendor, order_product_data["product"])
                OrderProduct.objects.create(
                    order=order,
                    product=product,
                    quantity=order_product_data["quantity"],
                    unit_price=order_product_data["unit_price"],
                    status=order_product_data["status"],
                )
