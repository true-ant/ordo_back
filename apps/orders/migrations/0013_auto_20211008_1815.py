# Generated by Django 3.2.6 on 2021-10-08 18:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_auto_20210923_0950'),
        ('orders', '0012_auto_20211007_1300'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='cart',
            unique_together={('office', 'product')},
        ),
        migrations.RemoveField(
            model_name='cart',
            name='user',
        ),
    ]
