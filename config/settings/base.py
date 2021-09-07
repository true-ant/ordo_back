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

from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


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
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_rest_passwordreset",
    "corsheaders",
    "django_filters",
]

ORDO_APPS = [
    "apps.accounts.apps.AccountsConfig",
    "apps.common.apps.CommonConfig",
    "apps.orders.apps.OrdersConfig",
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
        "DIRS": [],
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

# STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
STAGE = os.environ.get("STAGE")

# Email Settings
DEFAULT_FROM_EMAIL = "noreply@joinordo.com"

# Frontend Settings
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# Celery Settings
CELERY_DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE")
CELERY_BROKER_URL = (os.getenv("REDIS_URL"),)
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL")
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

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
        "rest_framework_jwt.authentication.JSONWebTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
}

# DRF-JWT
JWT_AUTH = {
    "JWT_EXPIRATION_DELTA": datetime.timedelta(days=3),
    "JWT_RESPONSE_PAYLOAD_HANDLER": "apps.accounts.utils.jwt_response_payload_handler",
}

# AWS
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME")
AWS_SES_REGION_ENDPOINT = os.getenv("AWS_SES_REGION_ENDPOINT")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_DEFAULT_ACL = None
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

AWS_LOCATION = "static"
STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

PUBLIC_MEDIA_LOCATION = "media"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"
DEFAULT_FILE_STORAGE = "apps.common.storage_backends.PublicMediaStorage"
