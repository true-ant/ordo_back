# Generated by Django 3.2.6 on 2021-10-12 20:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='officevendor',
            name='username',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
