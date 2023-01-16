
from django.db import migrations

INSERT_SLUGS_SQL = """
INSERT INTO orders_procedurecategorylink (proccat)
SELECT DISTINCT proccat FROM orders_procedurecode;
"""

class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0050_procedurecategorylink"),
    ]

    operations = [
        migrations.RunSQL(
            [INSERT_SLUGS_SQL],
        )
    ]
