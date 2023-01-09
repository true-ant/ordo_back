import asyncio
import datetime
import logging
import operator
from calendar import monthrange
from functools import reduce
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession, ClientTimeout
from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management import call_command
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.helper import OfficeBudgetHelper
from apps.accounts.models import CompanyMember, Office, OfficeVendor, User
from apps.orders.helpers import OfficeProductHelper
from apps.orders.models import OfficeProductCategory, OrderStatus, VendorOrder
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.accounts import CompanyInvite
from apps.vendor_clients.async_clients import BaseClient
import platform

if platform.system() == 'Windows':
   asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

UserModel = get_user_model()
logger = logging.getLogger(__name__)


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
        subject="Password Reset",
        message="message",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=htm_content,
    )


@shared_task
def send_welcome_email(user_id):
    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        return

    htm_content = render_to_string("emails/welcome.html")
    send_mail(
        subject="Welcome to Ordo!",
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
                "inviter": company_member.invited_by,
                "company": company_member.company,
                "TOKEN": company_member.token,
                "SITE_URL": settings.SITE_URL,
            },
        )
        send_mail(
            subject="You've been invited to Join Ordo!",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[company_member.email],
            html_message=htm_content,
        )


async def get_orders(office_vendor, login_cookies, perform_login, completed_order_ids):
    async with ClientSession(cookies=login_cookies, timeout=ClientTimeout(30)) as session:
        vendor = office_vendor.vendor
        scraper = ScraperFactory.create_scraper(
            vendor=vendor,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )

        orders = await scraper.get_orders(
            office=office_vendor.office, perform_login=perform_login, completed_order_ids=completed_order_ids
        )
        orders = sorted(orders, key=lambda x: x.order_date)
        if len(orders):
            first_order_date = orders[0].order_date
            first_order_date -= relativedelta(days=1)
        else:
            first_order_date = timezone.now().date() - relativedelta(days=1)

        await scraper.get_orders(
            office=office_vendor.office,
            from_date=first_order_date - relativedelta(months=12),
            to_date=first_order_date,
            completed_order_ids=completed_order_ids,
        )

        # if vendor.slug == "ultradent":
        #     await scraper.get_all_products_v2(office_vendor.office)


@shared_task
def fetch_vendor_products_prices(office_vendor_id):
    print("fetch_vendor_products_prices")
    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    asyncio.run(
        OfficeProductHelper.get_all_product_prices_from_vendors(
            office_id=office_vendor.office.id, vendor_slugs=[office_vendor.vendor.slug]
        )
    )
    print("fetch_vendor_products_prices DONE")


@shared_task
def update_net32_vendor_products_prices():
    print("====update_net32_vendor_products_prices====")
    office_vendors = OfficeVendor.objects.select_related("office", "vendor").filter(vendor__slug="net_32")

    for office_vendor in office_vendors:
        asyncio.run(
            OfficeProductHelper.get_all_product_prices_from_vendors(
                office_id=office_vendor.office.id, vendor_slugs=[office_vendor.vendor.slug]
            )
        )
    print("update_net32_vendor_products_prices DONE")


@shared_task
def fetch_orders_from_vendor(office_vendor_id, login_cookies=None, perform_login=False):
    if login_cookies is None and perform_login is False:
        return

    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    # offices_vendors = OfficeVendor.objects.filter(
    #     office__company=office_vendor.office.company, vendor=office_vendor.vendor
    # )

    if not OfficeProductCategory.objects.filter(office=office_vendor.office).exists():
        call_command("fill_office_product_categories", office_ids=[office_vendor.office.id])

    if login_cookies:
        cookie = SimpleCookie()
        for login_cookie in login_cookies.split("\r\n"):
            login_cookie = login_cookie.replace("Set-Cookie: ", "")
            cookie.load(login_cookie)
    else:
        cookie = None

    order_id_field = "vendor_order_reference" if office_vendor.vendor.slug == "henry_schein" else "vendor_order_id"
    completed_order_ids = list(
        VendorOrder.objects.filter(
            vendor=office_vendor.vendor, order__office=office_vendor.office, status=OrderStatus.CLOSED
        ).values_list(order_id_field, flat=True)
    )
    print("========== completed order ids==========")
    print(completed_order_ids)
    asyncio.run(get_orders(office_vendor, cookie, True, completed_order_ids))
    # office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    # asyncio.run(
    #     OfficeProductHelper.get_all_product_prices_from_vendors(
    #         office_id=office_vendor.office.id, vendor_slugs=[office_vendor.vendor.slug]
    #     )
    # )

    # inventory group products
    # office_vendors = OfficeVendor.objects.select_related("office", "vendor").filter(office=office_vendor.office)
    # if office_vendors.count() > 1:
    #     vendors_products = []
    #     for office_vendor in office_vendors:
    #         product_ids = OfficeProduct.objects.filter(
    #             is_inventory=True, product__vendor=office_vendor.vendor
    #         ).values_list("product__product_id", flat=True)
    #         if product_ids:
    #             vendors_products.append(
    #                 Product.objects.filter(
    #                     vendor=office_vendor.vendor, parent__isnull=True, product_id__in=product_ids
    #                 )
    #             )
    
    #     if len(vendors_products) > 1:
    #         group_products(vendors_products, model=True)

    # TODO: iterate keyword tables. fetch products for keyword and pricing comparison

    # with transaction.atomic():
    #     for order_data_cls in orders:
    #         order_data = order_data_cls.to_dict()
    #         shipping_address = order_data.pop("shipping_address")
    #         try:
    #             office = [
    #                 office_vendor.office
    #                 for office_vendor in offices_vendors
    #                 if office_vendor.office.shipping_zip_code[:5] == shipping_address["postal_code"][:5]
    #             ][0]
    #         except (TypeError, IndexError):
    #             office = office_vendor.office

    #         save_order_to_db(office, office_vendor.vendor, order_data)
    #         office_vendor.task_id = ""
    #         office_vendor.save()


@shared_task
def send_budget_update_notification():
    today = timezone.now().date()
    last_day = monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return

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
            subject="It's time to update your budget!",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            html_message=htm_content,
        )


@shared_task
def update_office_budget():
    OfficeBudgetHelper.update_budget_with_previous_month()


#####################################################################################################################
# v2
#####################################################################################################################


async def get_orders_v2(office_vendor, completed_order_ids):

    async with ClientSession(timeout=ClientTimeout(30)) as session:
        vendor = office_vendor.vendor
        client = BaseClient.make_handler(
            vendor_slug=vendor.slug,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )
        from_date = timezone.now().date()
        to_date = from_date - relativedelta(year=1)
        orders = await client.get_orders(from_date=from_date, to_date=to_date, exclude_order_ids=completed_order_ids)


@shared_task
def fetch_orders_v2(office_vendor_id):
    """
    this is used for fetching implant orders only, but in the future, we should fetch orders using this
    """

    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)

    if not OfficeProductCategory.objects.filter(office=office_vendor.office).exists():
        call_command("fill_office_product_categories", office_ids=[office_vendor.office.id])

    order_id_field = "vendor_order_reference" if office_vendor.vendor.slug == "henry_schein" else "vendor_order_id"

    completed_order_ids = list(
        VendorOrder.objects.filter(
            vendor=office_vendor.vendor, order__office=office_vendor.office, status=OrderStatus.CLOSED
        ).values_list(order_id_field, flat=True)
    )
    asyncio.run(get_orders_v2(office_vendor, completed_order_ids))
