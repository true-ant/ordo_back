from .base import *  # noqa

EMAIL_BACKEND = "django_ses.SESBackend"
ALLOWED_HOSTS = ["ordo-backend-dev.us-east-1.elasticbeanstalk.com"]

CELERY_RESULT_BACKEND = None

BROKER_TRANSPORT_OPTIONS = {
    "polling_interval": 20,
    "region": "us-east-1",
}
BROKER_URL = f"sqs://{AWS_ACCESS_KEY_ID}:{AWS_SECRET_ACCESS_KEY}@"  # noqa
CELERY_BROKER_URL = BROKER_URL
CORS_ALLOW_ALL_ORIGINS = True
