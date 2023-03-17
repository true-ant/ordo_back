from django.db import models

from apps.accounts.models import User


class ProductParentHistory(models.Model):
    operation_id = models.UUIDField()
    product = models.IntegerField()
    old_parent = models.IntegerField(null=True)
    new_parent = models.IntegerField(null=True)


class SearchHistory(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    query = models.CharField(max_length=1024)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
