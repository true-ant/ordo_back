import asyncio
import csv
import logging
import operator
import os
import platform
import traceback
from functools import reduce
from typing import List

import pysftp
from aiohttp import ClientSession, ClientTimeout
from celery import states
from celery.exceptions import Ignore
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management import call_command
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.errors import TaskFailure
from apps.accounts.helper import OfficeBudgetHelper
from apps.accounts.models import CompanyMember, Office, OfficeVendor, User
from apps.orders.helpers import (
    OfficeProductCategoryHelper,
    OfficeProductHelper,
    OrderHelper,
)
from apps.orders.models import OfficeProductCategory, OrderStatus, VendorOrder
from apps.orders.product_updater import update_vendor_products_by_api
from apps.orders.products_updater.net32_updater import update_net32_products
from apps.orders.updater import fetch_for_vendor
from apps.scrapers.errors import ScraperException
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


@app.task(bind=True)
def update_vendor_products_prices(self, vendor_slug, office_id=None):
    try:
        asyncio.run(fetch_for_vendor(vendor_slug, office_id))
    except ScraperException as e:
        self.update_state(state=states.FAILURE, meta=traceback.format_exc())
        raise Ignore() from e


@app.task
def update_vendor_product_prices_for_all_offices(vendor_slug):
    for ov in OfficeVendor.objects.filter(vendor__slug=vendor_slug):
        update_vendor_products_prices.delay(vendor_slug, ov.office_id)
    OrderHelper.update_vendor_order_product_price(vendor_slug)


@app.task
def update_vendor_products_by_api_for_all_offices(vendor_slug):
    asyncio.run(update_vendor_products_by_api(vendor_slug))
    OrderHelper.update_vendor_order_product_price(vendor_slug)


@app.task
def task_update_net32_products():
    asyncio.run(update_net32_products())


@app.task
def link_vendor(vendor_slug: str, office_id: int, consider_recent=False):
    call_command("fill_office_products", office=office_id, vendor=vendor_slug)
    fetch_order_history(vendor_slug, office_id, consider_recent)


@app.task
def fetch_order_history(vendor_slug, office_id, consider_recent=False):
    """
    NOTE: Passed vendor_slug and office_id as params instead of OfficeVendor object
    to clearly observe task events in the celery flower...
    """
    if not OfficeProductCategory.objects.filter(office=office_id).exists():
        OfficeProductCategoryHelper.create_categories_from_product_category(office_id)

    office_vendor = OfficeVendor.objects.get(vendor__slug=vendor_slug, office=office_id)

    if not office_vendor.login_success:
        raise TaskFailure("The authentication of this vendor doesn't work.")

    order_id_field = "vendor_order_reference" if vendor_slug == "henry_schein" else "vendor_order_id"
    completed_order_ids = list(
        VendorOrder.objects.filter(
            vendor=office_vendor.vendor, order__office=office_vendor.office, status=OrderStatus.CLOSED
        ).values_list(order_id_field, flat=True)
    )
    asyncio.run(
        OrderHelper.fetch_orders_and_update(
            office_vendor=office_vendor, completed_order_ids=completed_order_ids, consider_recent=consider_recent
        )
    )


@app.task
def update_order_history_for_all_offices(vendor_slug):
    office_vendors = OfficeVendor.objects.filter(vendor__slug=vendor_slug)
    for ov in office_vendors:
        fetch_order_history.delay(vendor_slug, ov.office_id, True)


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


@app.task
def notify_vendor_auth_issue_to_admins(office_vendor_id):
    office_vendor = OfficeVendor.objects.get(pk=office_vendor_id)
    company_members = CompanyMember.objects.filter(office=office_vendor.office, role=User.Role.ADMIN).values_list(
        "user"
    )

    for company_member in company_members:
        user = company_member.user

        htm_content = render_to_string(
            "emails/vendor_unlink.html",
            {
                "vendor": office_vendor.vendor.name,
            },
        )

        send_mail(
            subject="Vendor authentication failure!",
            message="message",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=htm_content,
        )


@app.task
def generate_csv_for_salesforce():
    """
    NOTE: the logic needs to be updated a bit more.
    But, this is basically create csv file from office table and upload it into SFTP server
    """
    offices = Office.objects.all()

    if not offices.exists():
        # No data accidentally
        return

    office_data = []

    for idx, office in enumerate(offices):
        if idx == 0:
            target_columns = list(office.__dict__.keys())
            target_columns.remove("_state")
            target_columns.remove("company_id")
            target_columns.append("company_name")
            target_columns.append("company_slug")
            target_columns.append("onboarding_step")
            target_columns.append("email")
        data = office.__dict__
        data["company_name"] = office.company.name
        data["company_slug"] = office.company.slug
        data["onboarding_step"] = office.company.on_boarding_step
        data["created_at"] = data["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        data["updated_at"] = data["updated_at"].strftime("%Y-%m-%d %H:%M:%S")

        company_member_emails = office.companymember_set.values_list("email", flat=True)
        for member_email in company_member_emails:
            new_data = data.copy()
            new_data["email"] = member_email
            office_data.append(new_data)

    dict_columns = {i: i.title() for i in target_columns}
    host = os.getenv("SFTP_HOST")
    username = os.getenv("SFTP_USERNAME")
    password = os.getenv("SFTP_PASSWORD")
    port = os.getenv("SFTP_PORT")
    connection_options = pysftp.CnOpts()
    connection_options.hostkeys = None

    with pysftp.Connection(
        host=host, username=username, password=password, port=int(port), cnopts=connection_options
    ) as sftp:
        with sftp.open(f"/Import/customer_master{timezone.now().strftime('%Y%m%d')}.csv", mode="w") as csv_file:
            file_writer = csv.DictWriter(csv_file, fieldnames=dict_columns, extrasaction="ignore")
            file_writer.writerow(dict_columns)
            file_writer.writerows(office_data)
