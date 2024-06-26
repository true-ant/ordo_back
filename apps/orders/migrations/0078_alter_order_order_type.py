# Generated by Django 4.1.6 on 2023-05-03 18:17

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0077_child_count_vendors_triggers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="order_type",
            field=models.CharField(
                choices=[
                    ("redundancy", "Ordo Order - Redundancy"),
                    ("normal", "Ordo Order"),
                    ("vendor", "Vendor Direct"),
                ],
                default="redundancy",
                max_length=100,
            ),
        ),
    ]
