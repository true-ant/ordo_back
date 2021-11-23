from .base import *  # noqa

DEBUG = True

# Email settings
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = "/tmp/app-messages"
# CELERY_TASK_ALWAYS_EAGER=True
CORS_ALLOW_ALL_ORIGINS = True
