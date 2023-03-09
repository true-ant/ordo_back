# Generated by Django 4.1.6 on 2023-03-09 05:29

import django.contrib.postgres.search
from django.db import migrations, models

DROP_EXPRESSION_SQL = """
alter table orders_procedurecode alter column search_vector drop expression;
"""

DROP_SEARCH_VECTOR_SQL = """
ALTER TABLE orders_procedurecode DROP COLUMN search_vector;
"""

ADD_SEARCH_VECTOR_SQL = """
ALTER TABLE orders_procedurecode ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(proccode, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(abbr_desc,'')), 'B')
                ) STORED;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0059_procedurecode_abbr_desc_procedurecode_search_vector'),
    ]

    operations = [
        # migrations.RunSQL(ADD_SEARCH_VECTOR_SQL),
        migrations.RunSQL([DROP_EXPRESSION_SQL, DROP_SEARCH_VECTOR_SQL]),
        migrations.AddField(
            model_name='procedurecode',
            name='search_vector',
            field=django.contrib.postgres.search.SearchVectorField(blank=True, help_text='Search vector', null=True),
        ),
        migrations.AlterField(
            model_name='officeproduct',
            name='nickname',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.RunSQL(
            [DROP_SEARCH_VECTOR_SQL, ADD_SEARCH_VECTOR_SQL]
        )

    ]
