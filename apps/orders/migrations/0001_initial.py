# Generated by Django 3.2.6 on 2021-08-20 19:58

import django.db.models.deletion
from django.db import migrations, models

import apps.common.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order_id", models.CharField(max_length=100)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(max_length=100)),
                ("order_date", models.DateField()),
                ("status", models.CharField(max_length=100)),
                (
                    "office_vendor",
                    apps.common.models.FlexibleForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="accounts.officevendor"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("quantity", models.IntegerField(default=0)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(max_length=100)),
                (
                    "order",
                    apps.common.models.FlexibleForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="items", to="orders.order"
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
                "abstract": False,
            },
        ),
    ]