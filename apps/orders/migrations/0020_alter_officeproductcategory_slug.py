# Generated by Django 3.2.6 on 2022-02-21 22:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0019_auto_20220221_2205'),
    ]

    operations = [
        migrations.AlterField(
            model_name='officeproductcategory',
            name='slug',
            field=models.CharField(max_length=128),
        ),
    ]
