from django.db import models

PRODUCT_CATEGORY_STATS_BY_CATEGORY = """
WITH collapsed AS (
    SELECT DISTINCT ON (ofp.office_product_category_id, op.parent_id)
        ofp.id, ofp.vendor_id, ofp.office_product_category_id
        FROM "orders_officeproduct" ofp
            LEFT OUTER JOIN "orders_product" op ON (ofp.product_id = op.id)
        WHERE ofp.is_inventory AND ofp.office_id = 135
        ORDER BY ofp.office_product_category_id, op.parent_id ASC, ofp."last_order_date" DESC
    ),
    stats AS (
        SELECT
            COUNT(*) as count,
            array_agg(DISTINCT c.vendor_id) as vendors,
            c.office_product_category_id
        FROM collapsed c
        GROUP BY c.office_product_category_id
    )
SELECT ofc.*,
    ofc.slug != 'other' AS "has_category",
    office_product_category_id,
    stats.count as count,
    stats.vendors as vendors
    FROM stats
        JOIN orders_officeproductcategory ofc ON stats.office_product_category_id = ofc.id
    ORDER BY has_category DESC, ofc.name;
"""


class OfficeProductCategoryQuerySet(models.QuerySet):
    def with_stats(self, office_id):
        return self.raw(PRODUCT_CATEGORY_STATS_BY_CATEGORY, params={"office_id": office_id})


class OfficeProductCategoryManager(models.Manager):
    _queryset_class = OfficeProductCategoryQuerySet
