# Generated by Django 3.2.6 on 2022-03-23 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0027_alter_product_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeproduct',
            name='last_order_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='officeproduct',
            name='last_price_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
