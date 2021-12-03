import asyncio
import logging
import operator
from calendar import monthrange
from datetime import timedelta
from functools import reduce
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession
from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from month import Month

from apps.accounts.models import CompanyMember, Office, OfficeVendor, User
from apps.common.utils import group_products
from apps.orders.models import OfficeProduct, Product
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.accounts import CompanyInvite

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
        subject="Reset your Ordo password",
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


async def get_orders(office_vendor, login_cookies, perform_login):
    async with ClientSession(cookies=login_cookies) as session:
        vendor = office_vendor.vendor
        scraper = ScraperFactory.create_scraper(
            vendor=vendor,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )

        orders = await scraper.get_orders(
            office=office_vendor.office,
            perform_login=perform_login,
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
        )

        if vendor.slug == "ultradent":
            await scraper.get_all_products_v2(office_vendor.office)


@shared_task
def fetch_orders_from_vendor(office_vendor_id, login_cookies=None, perform_login=False):
    if login_cookies is None and perform_login is False:
        return

    # TODO: we don't have to fetch orders that already in our db
    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    # offices_vendors = OfficeVendor.objects.filter(
    #     office__company=office_vendor.office.company, vendor=office_vendor.vendor
    # )

    if login_cookies:
        cookie = SimpleCookie()
        for login_cookie in login_cookies.split("\r\n"):
            login_cookie = login_cookie.replace("Set-Cookie: ", "")
            cookie.load(login_cookie)
    else:
        cookie = None
    asyncio.run(get_orders(office_vendor, cookie, perform_login))

    # inventory group products
    office_vendors = OfficeVendor.objects.select_related("office", "vendor").filter(office=office_vendor.office)
    if office_vendors.count() > 1:
        vendors_products = []
        for office_vendor in office_vendors:
            product_ids = OfficeProduct.objects.filter(
                is_inventory=True, product__vendor=office_vendor.vendor
            ).values_list("product__product_id", flat=True)
            if product_ids:
                vendors_products.append(
                    Product.objects.filter(
                        vendor=office_vendor.vendor, parent__isnull=True, product_id__in=product_ids
                    )
                )

        if len(vendors_products) > 1:
            group_products(vendors_products, model=True)

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
            subject="Update your budget",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            html_message=htm_content,
        )


@shared_task
def update_office_budget():
    today = timezone.now().date()
    month_first_day = today.replace(day=1)
    current_month = Month(today.year, today.month)
    previous_month_last_day = (month_first_day - timedelta(days=1)).replace(day=1)
    previous_month = Month(previous_month_last_day.year, previous_month_last_day.month)

    offices = Office.objects.exclude(budgets__month=current_month)
    for office in offices:
        office_budget = office.budgets.get(month=previous_month)
        office_budget.id = None
        office_budget.dental_spend = 0
        office_budget.office_spend = 0
        office_budget.month = current_month
        office_budget.save()
