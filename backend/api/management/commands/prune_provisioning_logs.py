"""
Django management command to prune old provisioning logs based on project retention settings.
Run via: python manage.py prune_provisioning_logs
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import Project, ProvisioningLog


class Command(BaseCommand):
    help = 'Prune old provisioning logs based on project log_retention_days settings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--project-id',
            type=int,
            help='Only prune logs for a specific project ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        project_id = options.get('project_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No logs will be deleted'))

        # Get projects to process
        if project_id:
            projects = Project.objects.filter(id=project_id)
            if not projects.exists():
                self.stdout.write(self.style.ERROR(f'Project {project_id} not found'))
                return
        else:
            projects = Project.objects.all()

        total_pruned = 0
        now = timezone.now()

        for project in projects:
            # Skip projects with log_retention_days = 0 (keep forever)
            if project.log_retention_days == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Project {project.id} ({project.name}): log_retention_days=0, keeping all logs'
                    )
                )
                continue

            # Calculate cutoff date
            cutoff_date = now - timedelta(days=project.log_retention_days)

            # Find logs older than retention period
            old_logs = ProvisioningLog.objects.filter(
                project=project,
                timestamp__lt=cutoff_date
            )

            count = old_logs.count()
            if count == 0:
                self.stdout.write(
                    f'Project {project.id} ({project.name}): No logs to prune (retention: {project.log_retention_days} days)'
                )
                continue

            if not dry_run:
                old_logs.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Project {project.id} ({project.name}): Pruned {count} logs older than {project.log_retention_days} days'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Project {project.id} ({project.name}): Would prune {count} logs older than {project.log_retention_days} days'
                    )
                )

            total_pruned += count

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'\nDRY RUN: Would have pruned {total_pruned} total logs')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully pruned {total_pruned} total logs')
            )
