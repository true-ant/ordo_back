# Generated by Django 3.2.6 on 2021-11-23 17:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_cart_instant_checkout'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='order',
            options={'ordering': ('-order_date', '-updated_at')},
        ),
    ]
