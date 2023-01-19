# Generated by Django 3.2.13 on 2023-01-19 17:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0049_officeproduct_nn_vector'),
    ]

    operations = [
        migrations.RunSQL("DELETE FROM orders_cart WHERE unit_price IS NULL", migrations.RunSQL.noop),
        migrations.AlterField(
            model_name='cart',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]
