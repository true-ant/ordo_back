# Generated by Django 3.2.6 on 2022-04-14 12:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_auto_20220411_2151'),
    ]

    operations = [
        migrations.AddField(
            model_name='officebudget',
            name='miscellaneous_spend',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]