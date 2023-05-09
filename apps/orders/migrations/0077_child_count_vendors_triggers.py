# Generated by Django 4.1.6 on 2023-04-30 17:49

from django.db import migrations

RECALCULATE_VENDOR_IDS_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION parent_recalculate_children(parent_product_id bigint) RETURNS VOID
AS $$
BEGIN
    WITH child_aggs as (
        SELECT coalesce(array_agg(DISTINCT op.vendor_id), '{}') as calculated_vendor_ids, count(*) as calculated_child_count
        FROM orders_product op
        WHERE op.parent_id = parent_product_id
    )
    UPDATE orders_product
    SET vendors = calculated_vendor_ids, child_count = calculated_child_count
    FROM child_aggs ca
    WHERE id = parent_product_id;
END;
$$ LANGUAGE plpgsql;
"""

RECALCULATE_VENDOR_IDS_FUNCTION_REV_SQL = """
DROP FUNCTION IF EXISTS parent_recalculate_children(parent_product_id bigint);
"""

VENDOR_ID_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION tgf_parent_recalculate_children () RETURNS TRIGGER
AS $$
BEGIN
IF (TG_OP = 'DELETE') THEN
   PERFORM parent_recalculate_children(old.parent_id);
ELSIF (TG_OP = 'INSERT') THEN
   PERFORM parent_recalculate_children(new.parent_id);
ELSIF (TG_OP = 'UPDATE') THEN
   IF old.parent_id IS DISTINCT FROM new.parent_id THEN
      -- Choose which to update
      IF old.parent_id IS NOT NULL THEN
        PERFORM parent_recalculate_children(old.parent_id);
      END IF;
      IF new.parent_id IS NOT NULL THEN
        PERFORM parent_recalculate_children(new.parent_id);
      END IF;
   ElSE  -- just update one, they are the same
    PERFORM parent_recalculate_children(new.parent_id);
   END IF;
END IF;
IF (TG_OP = 'INSERT') OR (TG_OP = 'UPDATE') THEN
   RETURN NEW;
ELSIF (TG_OP = 'DELETE') THEN
   RETURN OLD;
END IF;
END;
$$ LANGUAGE plpgsql;
"""

VENDOR_ID_TRIGGER_SQL_REV = """
DROP FUNCTION IF EXISTS tgf_parent_recalculate_children ();
"""

TRIGGER_SQL = """
CREATE TRIGGER after_update_vendor_id_recalculate_children
AFTER UPDATE ON orders_product
FOR EACH ROW
WHEN ((old.vendor_id IS DISTINCT FROM new.vendor_id) OR (old.parent_id IS DISTINCT FROM new.parent_id))
EXECUTE FUNCTION tgf_parent_recalculate_children();

CREATE TRIGGER after_create_orders_product_recalculate_children
AFTER INSERT ON orders_product
FOR EACH ROW
WHEN (new.parent_id IS NOT NULL)
EXECUTE FUNCTION tgf_parent_recalculate_children();

CREATE TRIGGER after_delete_orders_product_recalculate_children
AFTER DELETE ON orders_product
FOR EACH ROW
WHEN (old.parent_id IS NOT NULL)
EXECUTE FUNCTION tgf_parent_recalculate_children();
"""

TRIGGER_SQL_REV = """
DROP TRIGGER after_update_vendor_id_recalculate_children ON orders_product;
DROP TRIGGER after_create_orders_product_recalculate_children ON orders_product;
DROP TRIGGER after_delete_orders_product_recalculate_children ON orders_product;
"""

class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0076_fill_vendor_ids"),
    ]

    operations = [
        migrations.RunSQL(
            RECALCULATE_VENDOR_IDS_FUNCTION_SQL, RECALCULATE_VENDOR_IDS_FUNCTION_REV_SQL
        ),
        migrations.RunSQL(
            VENDOR_ID_TRIGGER_SQL, VENDOR_ID_TRIGGER_SQL_REV
        ),
        migrations.RunSQL(
            TRIGGER_SQL, TRIGGER_SQL_REV
        )
    ]