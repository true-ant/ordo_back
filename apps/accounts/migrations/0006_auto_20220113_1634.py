# Generated by Django 3.2.6 on 2022-01-13 16:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_companymember_invited_by'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='companymember',
            options={'ordering': ('-updated_at',)},
        ),
        migrations.AlterUniqueTogether(
            name='companymember',
            unique_together=set(),
        ),
    ]