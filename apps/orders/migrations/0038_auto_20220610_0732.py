# Generated by Django 3.2.13 on 2022-06-10 07:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0037_product_product_name_gin_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='last_price_updated',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='officeproduct',
            name='last_price_updated',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
