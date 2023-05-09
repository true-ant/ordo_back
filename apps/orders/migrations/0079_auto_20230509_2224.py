# Generated by Django 4.2.1 on 2023-05-09 22:24

from django.db import migrations

UPDATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION recalculate_search_vector(parent_product_id bigint) RETURNS VOID
AS $$
BEGIN
    WITH child_aggs as (
        SELECT string_agg(op.name, ' ') as name,
               string_agg(op.product_id, ' ') as product_id,
               string_agg(replace(op.manufacturer_number, '-', ' '), ' ') as manufacturer_number
        FROM orders_product op
        WHERE op.parent_id = parent_product_id
    )
    UPDATE orders_product
    SET search_vector = setweight(to_tsvector('english', coalesce(ca.product_id, '')), 'A') ||
                        setweight(to_tsvector('english', coalesce(ca.manufacturer_number, '')), 'A') ||
                        setweight(to_tsvector('english', coalesce(ca.name, '')), 'B')
    FROM child_aggs ca
    WHERE id = parent_product_id;
END;
$$ LANGUAGE plpgsql;
"""

RECALCULATE_SQL = """
WITH parent_ids AS (
    SELECT DISTINCT parent_id FROM orders_product
)
SELECT recalculate_search_vector(parent_id)
FROM parent_ids
"""
class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0078_alter_order_order_type"),
    ]

    operations = [
        migrations.RunSQL(UPDATE_TRIGGER_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(RECALCULATE_SQL, migrations.RunSQL.noop)
    ]
