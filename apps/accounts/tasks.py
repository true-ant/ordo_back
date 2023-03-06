import asyncio
import logging
import operator
import platform
from functools import reduce
from http.cookies import SimpleCookie
from typing import List

from aiohttp import ClientSession, ClientTimeout
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
from apps.orders.helpers import (
    OfficeProductCategoryHelper,
    OfficeProductHelper,
    OrderHelper,
)
from apps.orders.models import OfficeProductCategory, OrderStatus, VendorOrder
from apps.orders.updater import fetch_for_vendor
from apps.types.accounts import CompanyInvite
from apps.vendor_clients.async_clients import BaseClient
from config.celery import app

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

UserModel = get_user_model()
logger = logging.getLogger(__name__)


@app.task
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


@app.task
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


@app.task
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


@app.task
def fetch_vendor_products_prices(office_vendor_id):
    print("fetch_vendor_products_prices")
    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)
    asyncio.run(
        OfficeProductHelper.get_all_product_prices_from_vendors(
            office_id=office_vendor.office.id, vendor_slugs=[office_vendor.vendor.slug]
        )
    )
    print("fetch_vendor_products_prices DONE")


@app.task
def update_vendor_products_prices(vendor_slug, office_id=None):
    asyncio.run(fetch_for_vendor(vendor_slug, office_id))


@app.task
def update_vendor_product_prices_for_all_offices(vendor_slug):
    for ov in OfficeVendor.objects.filter(vendor__slug=vendor_slug):
        update_vendor_products_prices.delay(vendor_slug, ov.office_id)


@app.task
def update_order_history(vendor_slug, office_id):
    """
    NOTE: Passed vendor_slug and office_id as params instead of OfficeVendor object
    to clearly observe task events in the celery flower...
    """
    if not OfficeProductCategory.objects.filter(office=office_id).exists():
        OfficeProductCategoryHelper.create_categories_from_product_category(office_id)

    office_vendor = OfficeVendor.objects.get(vendor__slug=vendor_slug, office=office_id)
    order_id_field = "vendor_order_reference" if vendor_slug == "henry_schein" else "vendor_order_id"
    completed_order_ids = list(
        VendorOrder.objects.filter(
            vendor=office_vendor.vendor, order__office=office_vendor.office, status=OrderStatus.CLOSED
        ).values_list(order_id_field, flat=True)
    )
    asyncio.run(
        OrderHelper.fetch_orders_and_update(
            office_vendor=office_vendor, completed_order_ids=completed_order_ids, consider_recent=True
        )
    )


@app.task
def update_order_history_for_all_offices(vendor_slug):
    office_vendors = OfficeVendor.objects.filter(vendor__slug=vendor_slug)
    for ov in office_vendors:
        update_order_history.delay(vendor_slug, ov.office_id)


@app.task
def fetch_orders_from_vendor(office_vendor_id, login_cookies=None, perform_login=False):
    if login_cookies is None and perform_login is False:
        return

    office_vendor = OfficeVendor.objects.select_related("office", "vendor").get(id=office_vendor_id)

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
    asyncio.run(OrderHelper.fetch_orders_and_update((office_vendor, cookie, True, completed_order_ids)))


@app.task
def send_budget_update_notification():
    now_date = timezone.now().date()
    current_month = now_date.strftime("%B")
    previous_month = now_date - relativedelta(months=1)
    previous_month = previous_month.strftime("%B")
    offices = Office.objects.select_related("company").all()
    for office in offices:
        company_members = CompanyMember.objects.filter(
            office=office, role=User.Role.ADMIN, invite_status=CompanyMember.InviteStatus.INVITE_APPROVED
        )
        for member in company_members:
            if office.dental_api:
                htm_content = render_to_string(
                    "emails/updated_budget.html",
                    {
                        "SITE_URL": settings.SITE_URL,
                        "first_name": member.user.first_name,
                        "current_month": current_month,
                        "previous_month": previous_month,
                        "adjusted_production": office.budget.adjusted_production,
                        "collections": office.budget.collection,
                        "dental_percentage": office.budget.dental_percentage,
                        "dental_budget": office.budget.dental_budget,
                        "office_percentage": office.budget.office_percentage,
                        "office_budget": office.budget.office_budget,
                    },
                )
                send_mail(
                    subject="Your budget has automatically updated!",
                    message="message",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[member.email],
                    html_message=htm_content,
                )
            else:
                htm_content = render_to_string(
                    "emails/update_budget.html",
                    {"SITE_URL": settings.SITE_URL, "first_name": "Alex"},
                )
                send_mail(
                    subject="It's time to update your budget!",
                    message="message",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[member.email],
                    html_message=htm_content,
                )


@app.task
def update_office_budget():
    OfficeBudgetHelper.update_office_budgets()
    # OfficeBudgetHelper.update_budget_with_previous_month()


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
        await client.get_orders(from_date=from_date, to_date=to_date, exclude_order_ids=completed_order_ids)


@app.task
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
