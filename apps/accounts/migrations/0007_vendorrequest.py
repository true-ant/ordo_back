# Generated by Django 3.2.6 on 2022-03-03 15:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_auto_20220113_1634'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vendor_name', models.CharField(max_length=128)),
                ('description', models.TextField(blank=True, null=True)),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_requests', to='accounts.company')),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
    ]
