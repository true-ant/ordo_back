# Celery Settings
import os

import dotenv
from celery.schedules import crontab

dotenv.load_dotenv()


default_queue = os.getenv("CELERY_DEFAULT_QUEUE")
broker_url = (os.getenv("REDIS_URL"),)
result_backend = os.getenv("REDIS_URL")
# BROKER_TRANSPORT_OPTIONS = {
#    "polling_interval": 2,
#    "region": "us-east-1",
# }
# BROKER_URL = f"sqs://{AWS_ACCESS_KEY_ID}:{AWS_SECRET_ACCESS_KEY}@"  # noqa
# BROKER_URL = f"sqs://{AWS_ACCESS_KEY_ID}:{AWS_SECRET_ACCESS_KEY}@"
# RESULT_BACKEND = None
accept_content = ["application/json"]
task_serializer = "json"
result_serializer = "json"
# timezone = TIME_ZONE


beat_schedule = {
    "update_office_budget": {
        "task": "apps.accounts.tasks.update_office_budget",
        "schedule": crontab(hour=0, minute=0, day_of_month=1),
    },
    "send_budget_update_notification": {
        "task": "apps.accounts.tasks.send_budget_update_notification",
        "schedule": crontab(hour=0, minute=0),
    },
    "update_office_cart_status": {
        "task": "apps.orders.tasks.update_office_cart_status",
        "schedule": crontab(minute="*/10"),
    },
    "sync_with_vendors": {
        "task": "apps.orders.tasks.sync_with_vendors",
        "schedule": crontab(minute=0, hour=0),
    },
    "update_net32_vendor_products_prices": {
        "task": "apps.accounts.tasks.update_vendor_products_prices",
        "args": ("net_32",),
        "schedule": crontab(minute="*/10"),
    },
    "update_vendor_product_prices_for_henry_schein": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("henry_schein",),
        "schedule": crontab(minute="*/5"),
    },
    "update_vendor_product_prices_for_benco": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("benco",),
        "schedule": crontab(minute="*/5"),
    },
    "update_vendor_product_prices_for_darby": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("darby",),
        "schedule": crontab(minute="*/10"),
    },
    "update_vendor_product_prices_for_dental_city": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("dental_city",),
        "schedule": crontab(minute="*/10"),
    },
    "update_vendor_product_prices_for_edge_endo": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("edge_endo",),
        "schedule": crontab(minute="*/5"),
    },
    "update_vendor_product_prices_for_patterson": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("patterson",),
        "schedule": crontab(minute="*/5"),
    },
    "update_vendor_product_prices_for_ultradent": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("ultradent",),
        "schedule": crontab(minute="*/5"),
    },
    "update_vendor_product_prices_for_midwest_dental": {
        "task": "apps.accounts.tasks.update_vendor_product_prices_for_all_offices",
        "args": ("midwest_dental",),
        "schedule": crontab(minute="*/5"),
    },
    "update_order_history_for_net_32": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("net_32",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_henry_schein": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("henry_schein",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_benco": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("benco",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_darby": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("darby",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_dental_city": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("dental_city",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_implant_direct": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("implant_direct",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_order_history_for_patterson": {
        "task": "apps.accounts.tasks.update_order_history_for_all_offices",
        "args": ("patterson",),
        "schedule": crontab(day_of_week="1-5", hour=1, minute=0),
    },
    "update_promotions": {
        "task": "apps.orders.tasks.update_promotions",
        "schedule": crontab(minute="0", hour="0", day_of_week="3"),  # Every wednesday
    },
}
