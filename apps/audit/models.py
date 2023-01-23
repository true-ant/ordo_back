from django.db import models

from apps.accounts.models import User


class ProductRelationHistory(models.Model):
    before = models.JSONField()
    after = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)
