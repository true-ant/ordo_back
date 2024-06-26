# Generated by Django 3.2.13 on 2023-01-20 19:05

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0052_alter_cart_unit_price'),
    ]

    operations = [
        migrations.RenameField(
            model_name='procedurecategorylink',
            old_name='summary_category',
            new_name='summary_slug',
        ),
        migrations.AddField(
            model_name='procedurecategorylink',
            name='category_order',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='procedurecategorylink',
            name='is_favorite',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='procedurecode',
            name='summary_category',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='orders.procedurecategorylink'),
        ),
    ]
