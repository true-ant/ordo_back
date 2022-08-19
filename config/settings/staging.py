from .base import *  # noqa

DEBUG = True
SITE_URL = "https://staging.joinordo.com"
EMAIL_HOST = "smtp.mailgun.org"
EMAIL_PORT = 587
EMAIL_HOST_USER = EMAIL_HOST_USER  # noqa
EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD  # noqa
EMAIL_USE_TLS = True

ALLOWED_HOSTS = [
    "ordo-backend-dev.us-east-1.elasticbeanstalk.com",
    "api.staging.joinordo.com",
    "172.31.29.138",
    "172.31.8.130",
    "54.165.80.134",
    "127.0.0.1",
	"172.31.31.78",
    "localhost"
]
# CORS_ALLOWED_ORIGINS = [
#     "https://staging.joinordo.com",
#     "https://local.joinordo.com:8080",
#     "http://local.joinordo.com:8080",
# ]
CORS_ALLOW_ALL_ORIGINS = True

CELERY_RESULT_BACKEND = None
BROKER_TRANSPORT_OPTIONS = {
    "polling_interval": 2,
    "region": "us-east-1",
}
BROKER_URL = f"sqs://{AWS_ACCESS_KEY_ID}:{AWS_SECRET_ACCESS_KEY}@"  # noqa
CELERY_BROKER_URL = BROKER_URL
