# Generated by Django 4.1.5 on 2023-03-30 15:30

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0065_shippingmethod_value'),
    ]

    operations = [
        migrations.DeleteModel(
            name='OfficeVendorShippingOptions',
        ),
        migrations.DeleteModel(
            name='ShippingMethod',
        ),
    ]
