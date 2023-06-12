# Generated by Django 4.2.1 on 2023-06-12 19:40

import django.db.models.deletion
from django.db import migrations

import apps.common.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_fill_new_budget_tables"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companymember",
            name="company",
            field=apps.common.models.FlexibleForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="members", to="accounts.company"
            ),
        ),
    ]