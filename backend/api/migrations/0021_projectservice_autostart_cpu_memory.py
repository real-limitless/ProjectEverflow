# Generated migration for ProjectService autostart, cpu_limit, memory_limit fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_project_log_retention_days_provisioninglog'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectservice',
            name='autostart',
            field=models.BooleanField(default=False, help_text='Auto-start this service when workspace starts'),
        ),
        migrations.AddField(
            model_name='projectservice',
            name='cpu_limit',
            field=models.CharField(blank=True, help_text="CPU limit (e.g., '1.5' or '2')", max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='projectservice',
            name='memory_limit',
            field=models.CharField(blank=True, help_text="Memory limit (e.g., '512M' or '2G')", max_length=20, null=True),
        ),
    ]
