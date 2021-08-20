from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-updated_at",)


class FlexibleForeignKey(models.ForeignKey):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("on_delete", models.CASCADE)
        super().__init__(*args, **kwargs)
