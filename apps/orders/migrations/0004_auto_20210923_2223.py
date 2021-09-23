# Generated by Django 3.2.6 on 2021-09-23 22:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_auto_20210920_1029'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_date',
            field=models.DateField(auto_now=True),
        ),
        migrations.AddField(
            model_name='order',
            name='total_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='order',
            name='total_items',
            field=models.IntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='vendororder',
            name='total_items',
            field=models.IntegerField(default=1),
        ),
    ]
