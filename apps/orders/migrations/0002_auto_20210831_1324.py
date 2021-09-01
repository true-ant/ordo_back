# Generated by Django 3.2.6 on 2021-08-31 13:24

import django.db.models.deletion
from django.db import migrations, models

import apps.common.models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_officevendor_unique_together'),
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.IntegerField(default=0)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(max_length=100)),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product_id', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('url', models.URLField(blank=True, null=True)),
                ('image', models.URLField(blank=True, null=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('retail_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('vendor', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='accounts.vendor')),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
        migrations.AlterModelOptions(
            name='order',
            options={'ordering': ['-order_date']},
        ),
        migrations.AlterField(
            model_name='order',
            name='office_vendor',
            field=apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='accounts.officevendor'),
        ),
        migrations.DeleteModel(
            name='OrderItem',
        ),
        migrations.AddField(
            model_name='orderproduct',
            name='order',
            field=apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, to='orders.order'),
        ),
        migrations.AddField(
            model_name='orderproduct',
            name='product',
            field=apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, to='orders.product'),
        ),
        migrations.AddField(
            model_name='order',
            name='products',
            field=models.ManyToManyField(through='orders.OrderProduct', to='orders.Product'),
        ),
    ]