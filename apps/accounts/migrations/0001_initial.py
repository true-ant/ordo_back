# Generated by Django 3.2.6 on 2021-09-14 10:48

import creditcards.models
import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
import phonenumber_field.modelfields
from django.conf import settings
from django.db import migrations, models

import apps.accounts.models
import apps.common.models
import apps.common.utils


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('role', models.IntegerField(choices=[(0, 'Owner'), (1, 'Admin'), (2, 'User')], default=1)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='users')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('on_boarding_step', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name_plural': 'Companies',
            },
        ),
        migrations.CreateModel(
            name='Office',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('name', models.CharField(max_length=100)),
                ('address', models.CharField(blank=True, max_length=100, null=True)),
                ('postal_code', models.CharField(blank=True, max_length=100, null=True)),
                ('phone_number', phonenumber_field.modelfields.PhoneNumberField(blank=True, max_length=128, null=True, region=None)),
                ('website', models.CharField(blank=True, max_length=100, null=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='offices')),
                ('budget', models.PositiveIntegerField(default=0)),
                ('cc_number', creditcards.models.CardNumberField(blank=True, max_length=25, null=True, verbose_name='Card Number')),
                ('cc_expiry', creditcards.models.CardExpiryField(blank=True, null=True, verbose_name='Expiration Date')),
                ('cc_code', creditcards.models.SecurityCodeField(blank=True, max_length=4, null=True, verbose_name='Security Code')),
                ('company', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offices', to='accounts.company')),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Vendor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=100)),
                ('url', models.CharField(max_length=100)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='vendors')),
            ],
        ),
        migrations.CreateModel(
            name='OfficeVendor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(max_length=100)),
                ('password', models.CharField(max_length=100)),
                ('office', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.office')),
                ('vendor', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.vendor')),
            ],
            options={
                'unique_together': {('office', 'vendor')},
            },
        ),
        migrations.AddField(
            model_name='office',
            name='vendors',
            field=models.ManyToManyField(through='accounts.OfficeVendor', to='accounts.Vendor'),
        ),
        migrations.CreateModel(
            name='CompanyMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('role', models.IntegerField(choices=[(0, 'Owner'), (1, 'Admin'), (2, 'User')], default=1)),
                ('email', models.EmailField(max_length=254)),
                ('invite_status', models.IntegerField(choices=[(0, 'Invite Sent'), (1, 'Invite Approved'), (2, 'Invite Declined')], default=0)),
                ('date_joined', models.DateTimeField(blank=True, null=True)),
                ('token', models.CharField(default=apps.common.utils.generate_token, max_length=64, unique=True)),
                ('token_expires_at', models.DateTimeField(default=apps.accounts.models.default_expires_at)),
                ('is_active', models.BooleanField(default=True)),
                ('company', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.company')),
                ('office', apps.common.models.FlexibleForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='accounts.office')),
                ('user', apps.common.models.FlexibleForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('company', 'email')},
            },
        ),
    ]
