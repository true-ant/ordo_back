from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0031_auto_20220330_0052'),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            sql="""
            CREATE TRIGGER orders_product_trigger
            BEFORE INSERT OR UPDATE OF product_id, name, search_vector
            ON orders_product
            FOR EACH ROW EXECUTE PROCEDURE
            tsvector_update_trigger(
              search_vector, 'pg_catalog.english', product_id, name);

            UPDATE orders_product SET search_vector = NULL;
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS orders_product_trigger
            ON orders_product;
            """),
    ]
