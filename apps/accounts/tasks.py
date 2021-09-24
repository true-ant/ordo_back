import asyncio
import operator
from functools import reduce
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string

from apps.accounts.models import CompanyMember, Office, OfficeVendor, User
from apps.orders.models import (
    Order,
    Product,
    ProductImage,
    VendorOrder,
    VendorOrderProduct,
)
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.accounts import CompanyInvite

UserModel = get_user_model()


@shared_task
def send_forgot_password_mail(user_id, token):
    user = UserModel.objects.get(pk=user_id)
    htm_content = render_to_string(
        "emails/reset_password.html",
        {
            "TOKEN": token,
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
    q = reduce(
        operator.or_,
        [
            Q(company_id=company_email_invite["company_id"]) & Q(email=company_email_invite["email"])
            for company_email_invite in company_email_invites
        ],
    )

    company_members = CompanyMember.objects.filter(q)
    for company_member in company_members:
        htm_content = render_to_string(
            "emails/invite.html",
            {
                "COMPANY_NAME": company_member.company.name,
                "TOKEN": company_member.token,
                "SITE_URL": settings.SITE_URL,
            },
        )
        send_mail(
            subject="You've been invited!",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[company_member.email],
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
def fetch_orders_from_vendor(office_vendor_id, login_cookies=None, perform_login=False):
    if login_cookies is None and perform_login is False:
        return

    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    offices_vendors = OfficeVendor.objects.filter(
        office__company=office_vendor.office.company, vendor=office_vendor.vendor
    )

    if login_cookies:
        cookie = SimpleCookie()
        for login_cookie in login_cookies.split("\r\n"):
            login_cookie = login_cookie.replace("Set-Cookie: ", "")
            cookie.load(login_cookie)
    else:
        cookie = None
    orders = asyncio.run(get_orders(office_vendor, cookie, perform_login))

    with transaction.atomic():
        for order_data_cls in orders:
            order_data = order_data_cls.to_dict()
            order_products_data = order_data.pop("products")
            shipping_address = order_data.pop("shipping_address")
            try:
                office = [
                    office_vendor.office
                    for office_vendor in offices_vendors
                    if office_vendor.office.shipping_zip_code[:5] == shipping_address["postal_code"][:5]
                ][0]
            except (TypeError, IndexError):
                office = office_vendor.office

            order = Order.objects.create(
                office=office,
                status=order_data["status"],
                order_date=order_data["order_date"],
            )
            vendor_order = VendorOrder.from_dataclass(vendor=office_vendor.vendor, order=order, dict_data=order_data)
            for order_product_data in order_products_data:
                print(order_product_data)
                order_product_data["product"].pop("vendor_id")
                order_product_images = order_product_data["product"].pop("images", [])
                product = Product.from_dataclass(office_vendor.vendor, order_product_data["product"])
                for order_product_image in order_product_images:
                    ProductImage.objects.create(
                        product=product,
                        image=order_product_image["image"],
                    )
                VendorOrderProduct.objects.create(
                    vendor_order=vendor_order,
                    product=product,
                    quantity=order_product_data["quantity"],
                    unit_price=order_product_data["unit_price"],
                    status=order_product_data["status"],
                )


@shared_task
def update_office_budget():
    offices = Office.objects.select_related("company").all()
    for office in offices:
        emails = CompanyMember.objects.filter(
            company=office.company, role=User.Role.ADMIN, invite_status=CompanyMember.InviteStatus.INVITE_APPROVED
        ).values_list("email", flat=True)

    htm_content = render_to_string(
        "emails/update_budget.html",
        {
            "SITE_URL": settings.SITE_URL,
        },
    )

    send_mail(
        subject="Update your budget",
        message="message",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=emails,
        html_message=htm_content,
    )
