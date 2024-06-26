# Generated by Django 4.1.5 on 2023-03-30 15:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_remove_vendor_shipping_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShippingMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('value', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='officevendor',
            name='default_shipping_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ov_default_shipping_option', to='accounts.shippingmethod'),
        ),
        migrations.AddField(
            model_name='officevendor',
            name='shipping_options',
            field=models.ManyToManyField(related_name='ov_shipping_options', to='accounts.shippingmethod'),
        ),
    ]
