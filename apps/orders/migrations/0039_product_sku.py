# Generated by Django 3.2.13 on 2022-06-21 17:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0038_auto_20220621_1605'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='sku',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]