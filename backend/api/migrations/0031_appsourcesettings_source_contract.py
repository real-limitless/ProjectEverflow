from django.db import migrations, models


def populate_source_contract_fields(apps, schema_editor):
    AppSourceSettings = apps.get_model('api', 'AppSourceSettings')

    for settings in AppSourceSettings.objects.select_related('app').all():
        provider = settings.source_provider
        app = settings.app

        if provider == 'docker-registry':
            settings.source_kind = 'container-image'
            settings.source_location = app.repository_url or settings.source_location or ''
            settings.build_context_path = ''
            settings.source_ref = settings.source_ref or 'latest'
            settings.watch_paths = []
            settings.submodules_enabled = False
        elif provider == 'raw-compose':
            settings.source_kind = 'raw-compose'
            settings.source_location = app.compose_path or settings.source_location or ''
            settings.build_context_path = ''
            settings.source_ref = ''
            settings.watch_paths = []
            settings.submodules_enabled = False
        else:
            settings.source_kind = 'git-repository'
            settings.source_location = app.repository_url or settings.source_location or ''
            settings.build_context_path = ''

        settings.save(
            update_fields=[
                'source_kind',
                'source_location',
                'build_context_path',
                'source_ref',
                'watch_paths',
                'submodules_enabled',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_appsourcesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsourcesettings',
            name='build_context_path',
            field=models.CharField(blank=True, default='', max_length=500),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='appsourcesettings',
            name='source_kind',
            field=models.CharField(choices=[('git-repository', 'Git repository'), ('raw-compose', 'Raw compose'), ('raw-dockerfile', 'Raw Dockerfile'), ('container-image', 'Container image')], default='git-repository', max_length=30),
        ),
        migrations.AddField(
            model_name='appsourcesettings',
            name='source_location',
            field=models.CharField(blank=True, default='', max_length=500),
            preserve_default=False,
        ),
        migrations.RunPython(populate_source_contract_fields, migrations.RunPython.noop),
    ]