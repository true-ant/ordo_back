# Generated by Django 3.2.6 on 2021-09-14 09:43

import creditcards.models
import phonenumber_field.modelfields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='vendors'),
        ),
        migrations.AlterField(
            model_name='office',
            name='cc_code',
            field=creditcards.models.SecurityCodeField(blank=True, max_length=4, null=True, verbose_name='Security Code'),
        ),
        migrations.AlterField(
            model_name='office',
            name='cc_expiry',
            field=creditcards.models.CardExpiryField(blank=True, null=True, verbose_name='Expiration Date'),
        ),
        migrations.AlterField(
            model_name='office',
            name='cc_number',
            field=creditcards.models.CardNumberField(blank=True, max_length=25, null=True, verbose_name='Card Number'),
        ),
        migrations.AlterField(
            model_name='office',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='offices'),
        ),
        migrations.AlterField(
            model_name='office',
            name='phone_number',
            field=phonenumber_field.modelfields.PhoneNumberField(blank=True, max_length=128, null=True, region=None),
        ),
        migrations.AlterField(
            model_name='user',
            name='avatar',
            field=models.ImageField(blank=True, null=True, upload_to='users'),
        ),
    ]
