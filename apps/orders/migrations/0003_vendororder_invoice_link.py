# Generated by Django 3.2.6 on 2021-10-24 06:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_favouriteproduct'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendororder',
            name='invoice_link',
            field=models.URLField(blank=True, null=True),
        ),
    ]
