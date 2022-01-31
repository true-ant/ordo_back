# Generated by Django 3.2.6 on 2022-01-31 08:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_auto_20220127_1729'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendororderproduct',
            name='status',
            field=models.CharField(choices=[('open', 'Open'), ('shipped', 'Shipped'), ('arrived', 'Arrived'), ('received', 'Received'), ('rejected', 'Rejected')], default='open', max_length=100),
        ),
    ]
