# Generated by Django 3.2.6 on 2022-02-24 12:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0020_alter_officeproductcategory_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeproductcategory',
            name='predefined',
            field=models.BooleanField(default=True),
        ),
    ]
