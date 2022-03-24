# Generated by Django 3.2.6 on 2022-02-28 20:11

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.common.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('root_object_id', models.PositiveIntegerField()),
                ('metadata', models.JSONField(blank=True, null=True)),
                ('event', models.CharField(db_index=True, help_text='The class name of the notification class used to send.', max_length=256)),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NotificationRecipient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('is_email_sent', models.BooleanField(db_index=True, default=False)),
                ('is_sms_sent', models.BooleanField(db_index=True, default=False)),
                ('is_push_sent', models.BooleanField(db_index=True, default=False)),
                ('push_context', models.JSONField(null=True)),
                ('notification', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_recipients', to='notifications.notification')),
                ('user', apps.common.models.FlexibleForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_recipients', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-updated_at',),
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='notification',
            name='recipients',
            field=models.ManyToManyField(through='notifications.NotificationRecipient', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='notification',
            name='root_content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
    ]