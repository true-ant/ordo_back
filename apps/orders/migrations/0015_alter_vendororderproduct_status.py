# Generated by Django 3.2.6 on 2022-02-03 14:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0014_auto_20220202_1513'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendororderproduct',
            name='status',
            field=models.CharField(choices=[('open', 'Processing'), ('shipped', 'Shipped'), ('arrived', 'Arrived'), ('received', 'Received'), ('rejected', 'Rejected')], default='open', max_length=100),
        ),
    ]