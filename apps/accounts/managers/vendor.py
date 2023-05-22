from django.db import models

PRODUCT_CATEGORY_STATS_BY_VENDOR = """
WITH collapsed AS (
    SELECT DISTINCT ON (op.parent_id) ofp.id, ofp.vendor_id, ofp.office_product_category_id
                          FROM "orders_officeproduct" ofp
                                   LEFT OUTER JOIN "orders_product" op ON (ofp.product_id = op.id)
                          WHERE ofp.is_inventory AND ofp.office_id = %(office_id)s
                          ORDER BY op.parent_id ASC, ofp."last_order_date" DESC
    ),
    stats AS (
        SELECT
            COUNT(*) as count,
            array_agg(DISTINCT c.office_product_category_id) as categories,
            c.vendor_id
        FROM collapsed c
        GROUP BY c.vendor_id
    )
SELECT av.*,
    stats.count as count,
    stats.categories as categories
    FROM stats
        JOIN accounts_vendor av ON stats.vendor_id = av.id
    ORDER BY av.name;
"""


class VendorQuerySet(models.QuerySet):
    def with_stats(self, office_id):
        return self.raw(PRODUCT_CATEGORY_STATS_BY_VENDOR, params={"office_id": office_id})


class VendorManager(models.Manager):
    _queryset_class = VendorQuerySet
