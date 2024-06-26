# Generated by Django 3.2.6 on 2022-06-02 23:29

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_officebudget_miscellaneous_spend'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='officevendor',
            options={'ordering': ('vendor__name',)},
        ),
        migrations.AddField(
            model_name='officevendor',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='officevendor',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
