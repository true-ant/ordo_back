from django.db.models import Manager


class BaseActiveManager(Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)
