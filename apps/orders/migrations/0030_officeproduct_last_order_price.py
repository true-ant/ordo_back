# Generated by Django 3.2.6 on 2022-03-29 17:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0029_officeproduct_product_vendor_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeproduct',
            name='last_order_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
