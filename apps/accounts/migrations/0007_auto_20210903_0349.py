# Generated by Django 3.2.6 on 2021-09-03 03:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_user_is_active'),
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