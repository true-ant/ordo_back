from django.db import models

from apps.accounts.models import User


class ProductRelationHistory(models.Model):
    before = models.JSONField()
    after = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)


class SearchHistory(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    query = models.CharField(max_length=1024)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
