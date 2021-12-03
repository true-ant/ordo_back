# Generated by Django 3.2.6 on 2021-12-02 19:57

import django_extensions.db.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20211117_2015'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(blank=True, editable=False, populate_from=['name']),
        ),
        migrations.AddField(
            model_name='office',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(blank=True, editable=False, populate_from=['name']),
        ),
    ]