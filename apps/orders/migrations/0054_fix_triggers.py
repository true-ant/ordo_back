# Generated by Django 3.2.13 on 2023-01-23 17:23

from django.db import migrations

UPDATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION recalculate_search_vector(parent_product_id bigint) RETURNS VOID
AS $$
BEGIN
    WITH child_aggs as (
        SELECT string_agg(op.name, ' ') as name, string_agg(op.product_id, ' ') as product_id
        FROM orders_product op
        WHERE op.parent_id = parent_product_id
    )
    UPDATE orders_product
    SET search_vector = setweight(to_tsvector('english', coalesce(ca.product_id, '')), 'A') ||
                        setweight(to_tsvector('english', coalesce(ca.name, '')), 'B')
    FROM child_aggs ca
    WHERE id = parent_product_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION parent_recalculate_search_vector () RETURNS TRIGGER
AS $$
BEGIN
IF (TG_OP = 'DELETE') THEN
   PERFORM recalculate_search_vector(old.parent_id);
ELSIF (TG_OP = 'INSERT') THEN
   PERFORM recalculate_search_vector(new.parent_id);
ELSIF (TG_OP = 'UPDATE') THEN
   IF old.parent_id IS DISTINCT FROM new.parent_id THEN
      -- Choose which to update
      IF old.parent_id IS NOT NULL THEN
        PERFORM recalculate_search_vector(old.parent_id);
      END IF;
      IF new.parent_id IS NOT NULL THEN
        PERFORM recalculate_search_vector(new.parent_id);
      END IF;
   ElSE  -- just update one, they are the same
    PERFORM recalculate_search_vector(new.parent_id);
   END IF;
END IF;

IF (TG_OP = 'INSERT') OR (TG_OP = 'UPDATE') THEN
   RETURN NEW;
END IF;
END;
$$
LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS after_update_search_fields ON orders_product;
CREATE TRIGGER after_update_search_fields
AFTER UPDATE ON orders_product
FOR EACH ROW
WHEN (
    new.parent_id IS DISTINCT FROM old.parent_id -- parent_id was set, unset or changed
    OR
    (
      new.parent_id IS NOT NULL  -- some child is being modified
      AND
      ( -- name or product_id are being modified
        (old.name IS DISTINCT FROM new.name) OR
        (old.product_id IS DISTINCT FROM new.product_id)
      )
    )
) EXECUTE FUNCTION parent_recalculate_search_vector();
"""

UPDATE_TRIGGER_SQL_REV = """
CREATE OR REPLACE FUNCTION parent_recalculate_search_vector () RETURNS TRIGGER
AS $$
DECLARE
 pid integer := 0;
BEGIN
IF (TG_OP = 'DELETE') THEN
   pid := old.parent_id;
ELSIF (TG_OP = 'INSERT') OR (TG_OP = 'UPDATE') THEN
   pid := new.parent_id;
END IF;

IF (TG_OP = 'INSERT') OR (TG_OP = 'UPDATE') THEN
   RETURN NEW;
END IF;
END;
$$
LANGUAGE plpgsql;

DROP FUNCTION recalculate_search_vector(parent_product_id bigint);

DROP TRIGGER IF EXISTS after_update_search_fields ON orders_product;

CREATE TRIGGER after_update_search_fields
AFTER UPDATE ON orders_product
FOR EACH ROW
WHEN (((old.name IS DISTINCT FROM new.name) OR (old.product_id IS DISTINCT FROM new.product_id))
      AND new.parent_id IS NOT NULL)
EXECUTE FUNCTION parent_recalculate_search_vector();



"""

class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0053_procedure_category_link'),
    ]

    operations = [
        migrations.RunSQL(UPDATE_TRIGGER_SQL, UPDATE_TRIGGER_SQL_REV)
    ]