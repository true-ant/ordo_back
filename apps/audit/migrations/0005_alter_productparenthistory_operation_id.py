# Generated by Django 4.1.6 on 2023-05-07 01:49

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0004_rollbackinformation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productparenthistory",
            name="operation_id",
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
