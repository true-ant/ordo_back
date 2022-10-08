import os
import html
from django.core.mail import send_mail
from django.template.loader import render_to_string
import datetime



SITE_URL = "https://staging.joinordo.com"
FROM_EMAIL = "noreply@joinordo.com"

class Company():
    def __init__(self, name) -> None:
        self.name = name

class Office():
    def __init__(self, name, addr = ""):
        self.name=name
        self.shipping_address = addr

class User():
    def __init__(self, name):
        self.full_name = name
def test_approval():
    # Approval Needed
    office = Office("Columbine Creek Dentistry")
    email_template = "order_approval_needed.html"
    htm_content = render_to_string(
        f"emails/{email_template}",
        {
            "order_created_by": None,
            "vendors": ["TestVendor1", "TestVendor2"],
            "vendor_order_ids": "12345",
            "order_date": datetime.datetime.now(),
            "total_items": 5,
            "total_amount": "$10000",
            "remaining_budget": 1000,
            "office": office,
            "SITE_URL": SITE_URL,
        },
    )
    send_mail(
        subject="Order approval needed",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list=list("zachburau@gmail.com"),
        html_message=htm_content,
    )

def test_confirmation():
    # Approval Needed
    office = Office("Columbine Creek Dentistry")
    email_template = "order_creation.html"
    htm_content = render_to_string(
        f"emails/{email_template}",
        {
            "order_created_by": None,
            "vendors": ["TestVendor1", "TestVendor2"],
            "vendor_order_ids": "12345",
            "order_date": datetime.datetime.now(),
            "total_items": 5,
            "total_amount": "$10000",
            "remaining_budget": 1000,
            "office": office,
            "SITE_URL": SITE_URL,
        },
    )
    send_mail(
        subject="Order Confirmation",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list=list("zachburau@gmail.com"),
        html_message=htm_content,
    )

def test_reset_password():
    htm_content = render_to_string(
        "emails/reset_password.html",
        {
            "TOKEN": "",
            "SITE_URL": SITE_URL,
        },
    )
    send_mail(
        subject="Password Reset",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list="zachburau@gmail.com",
        html_message=htm_content,
    )

def test_welcome_to_ordo():
    htm_content = render_to_string("emails/welcome.html")
    send_mail(
        subject="Welcome to Ordo!",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list="zachburau@gmail.com",
        html_message=htm_content,
    )

def test_invited():
    inviter = User("Test Inviter")
    company = Company("Columbine Creek Dentistry")
    htm_content = render_to_string(
        "emails/invite.html",
        {
            "inviter": inviter,
            "company": company,
            "TOKEN": "",
            "SITE_URL": SITE_URL,
        },
    )
    send_mail(
        subject="You've been invited to Join Ordo!",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list=["kisney.dev.11@gmail.com"],
        html_message=htm_content,
    )
    
def test_update_budget():
    htm_content = render_to_string(
        "emails/update_budget.html",
        {
            "SITE_URL": SITE_URL,
        },
    )

    send_mail(
        subject="It's time to update your budget!",
        message="message",
        from_email=FROM_EMAIL,
        recipient_list=list("zachburau@gmail.com"),
        html_message=htm_content,
    )
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apps.config.settings")
    test_invited()
    # test_welcome_to_ordo()
    # test_approval()
    # test_confirmation()
    # test_reset_password()
    # test_update_budget()
