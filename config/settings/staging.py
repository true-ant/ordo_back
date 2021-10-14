from .base import *  # noqa

DEBUG = True
EMAIL_HOST = "smtp.mailgun.org"
EMAIL_PORT = 587
EMAIL_HOST_USER = EMAIL_HOST_USER  # noqa
EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD  # noqa
EMAIL_USE_TLS = True

ALLOWED_HOSTS = [
    "ordo-backend-dev.us-east-1.elasticbeanstalk.com",
    "api.staging.joinordo.com",
]
CORS_ALLOWED_ORIGINS = [
    "https://staging.joinordo.com",
    "http://localhost:8080",
]
