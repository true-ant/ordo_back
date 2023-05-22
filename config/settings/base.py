"""
Django settings for ordo_backend project.

Generated by 'django-admin startproject' using Django 3.2.6.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""
import datetime
import os
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv

from services.utils.secrets import get_secret_value

# Build paths inside the project like this: BASE_DIR / 'subdir'.

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
ALLOWED_HOSTS = []


# Application definition

DANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_rest_passwordreset",
    "corsheaders",
    "django_filters",
    "phonenumber_field",
    "django_celery_beat",
    "nested_admin",
    "django_extensions",
]

ORDO_APPS = [
    "apps.accounts.apps.AccountsConfig",
    "apps.common.apps.CommonConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.audit.apps.AuditConfig",
]

INSTALLED_APPS = DANGO_APPS + THIRD_PARTY_APPS + ORDO_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("RDS_DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("RDS_DB_NAME", os.path.join(BASE_DIR, "db.sqlite3")),
        "USER": os.environ.get("RDS_USERNAME", "user"),
        "PASSWORD": os.environ.get("RDS_PASSWORD", "password"),
        "HOST": os.environ.get("RDS_HOSTNAME", "localhost"),
        "PORT": os.environ.get("RDS_PORT", "5432"),
        "TEST": {
            "NAME": "ordo_db_test",
        },
        "CONN_MAX_AGE": 1500,
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
STAGE = os.environ.get("STAGE")


# AWS
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME")
AWS_SES_REGION_ENDPOINT = os.getenv("AWS_SES_REGION_ENDPOINT")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_DEFAULT_ACL = None
AWS_S3_CUSTOM_DOMAIN = "cdn.staging.joinordo.com"
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

# Email Settings
DEFAULT_FROM_EMAIL = "Gordo from Ordo <noreply@joinordo.com>"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = get_secret_value("EMAIL_HOST_PASSWORD")

# Frontend Settings
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")


# Django Rest Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_RENDERER_CLASSES": [
        "apps.common.renders.APIRenderer",
    ],
    # "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    # "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
}

# DRF-JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": datetime.timedelta(days=3),
}

STATIC_LOCATION = "/static/"
STATICFILES_STORAGE = "apps.common.storage_backends.StaticStorage"

PUBLIC_MEDIA_LOCATION = "/media/"
DEFAULT_FILE_STORAGE = "apps.common.storage_backends.PublicMediaStorage"

# phone number field settings
PHONENUMBER_DB_FORMAT = "NATIONAL"
PHONENUMBER_DEFAULT_REGION = "US"

SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "UNKNOWN")

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    from .version import VERSION

    TRACES_SAMPLE_RATES = {"beanstalk": 1, "celery": 0.1}
    DEFAULT_TRACES_SAMPLE_RATE = 0.1

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=SENTRY_ENVIRONMENT,
        release=VERSION,
        traces_sample_rate=TRACES_SAMPLE_RATES.get(SENTRY_ENVIRONMENT, DEFAULT_TRACES_SAMPLE_RATE),
        send_default_pii=True,
    )

# Stripe
STRIPE_API_KEY = get_secret_value("STRIPE_API_KEY")
STRIPE_SUBSCRIPTION_PRICE_ID = os.getenv("STRIPE_SUBSCRIPTION_PRICE_ID")
MAKE_FAKE_ORDER = os.getenv("MAKE_FAKE_ORDER", True)
PRODUCT_PRICE_UPDATE_CYCLE = 14
NET32_PRODUCT_PRICE_UPDATE_CYCLE = 14
FORMULA_VENDORS = [
    "henry_schein",
    "darby",
    "patterson",
    "amazon",
    "benco",
    "ultradent",
    "implant_direct",
    "edge_endo",
    "dental_city",
    "dcdental",
    "crazy_dental",
    "purelife",
    "skydental",
    "top_glove",
    "bluesky_bio",
    "practicon",
    "midwest_dental",
    "pearson",
    "salvin",
    "bergmand",
    "biohorizons",
    "atomo",
    "orthoarch",
    "office_depot",
    "safco",
]
NON_FORMULA_VENDORS = [
    "net_32",
]
API_AVAILABLE_VENDORS = ["dental_city"]

RUNSERVER_PLUS_PRINT_SQL_TRUNCATE = None

# Vendor API Keys
DENTAL_CITY_AUTH_KEY = get_secret_value("DENTAL_CITY_AUTH_KEY")

CORS_EXPOSE_HEADERS = [
    "Content-Disposition",
]
