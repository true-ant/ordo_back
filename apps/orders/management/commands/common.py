from apps.orders.models import OfficeProductCategory, ProductCategory

product_categories = ProductCategory.objects.filter(slug="other")
for product_category in product_categories:
    product_category.name = "Uncategorized"
    product_category.save()


office_product_categories = OfficeProductCategory.objects.filter(slug="other")
for product_category in office_product_categories:
    product_category.name = "Uncategorized"
    product_category.save()
