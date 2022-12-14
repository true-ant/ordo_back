from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ProcedureCode',
            fields=[
                ('CodeNum', models.BigAutoField(primary_key=True, serialize=True)),
                ('ProcCode', models.CharField(max_length=16)),
                ('Descript', models.CharField(max_length=256, null=True, blank=True)),
                ('AbbrDesc', models.CharField(max_length=50, null=True, blank=True)),
                ('ProcCat', models.IntegerField(default=0)),
            ],
            options={
                'ordering': ('ProcCat')
            }
        )
    ]
