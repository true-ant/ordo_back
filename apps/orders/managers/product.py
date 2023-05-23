from django.contrib.postgres.search import SearchQuery
from django.db import models
from django.db.models import Q
from django.db.models.expressions import RawSQL

from apps.common.enums import SupportedVendor
from apps.common.utils import remove_dash_between_numerics


class ProductQuerySet(models.QuerySet):
    def search(self, text):
        # this is for search for henry schein product id
        text = remove_dash_between_numerics(text)
        # trigram_similarity = TrigramSimilarity("name", text)
        q = SearchQuery(text, config="english")
        return (
            self
            # .annotate(similarity=trigram_similarity)
            .filter(Q(search_vector=q))
        )

    def with_inventory_refs(self):
        return self.annotate(_inventory_refs=RawSQL("inventory_refs", (), output_field=models.IntegerField()))

    async def avalues_list(self, field):
        result = self.values_list(field, flat=True)
        return [x async for x in result.aiterator()]


class ProductManager(models.Manager):
    _queryset_class = ProductQuerySet

    def search(self, text):
        return self.get_queryset().search(text)

    def available_products(self):
        return self.get_queryset().filter(is_available_on_vendor=True)

    def unavailable_products(self):
        return self.get_queryset().filter(is_available_on_vendor=False)

    async def avalues_list(self, field):
        return await self.get_queryset().avalues_list(field)


class Net32ProductManager(ProductManager):
    def get_queryset(self):
        return super().get_queryset().filter(vendor__slug=SupportedVendor.Net32.value)
