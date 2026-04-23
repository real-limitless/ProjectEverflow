from django.core.management.base import BaseCommand
from api.models import Project, ProjectTool


class Command(BaseCommand):
    help = 'Create default execute-command tool for projects'

    def handle(self, *args, **options):
        projects = Project.objects.all()
        created_count = 0
        
        for project in projects:
            tool, created = ProjectTool.objects.get_or_create(
                project=project,
                slug='execute-command',
                defaults={
                    'name': 'Execute Command',
                    'description': 'Execute safe shell commands in project containers within /workspace',
                    'entrypoint': 'echo "Command execution tool - use TOOL_INPUT environment variable"',
                    'args_schema': {
                        'type': 'object',
                        'properties': {
                            'command': {
                                'type': 'string',
                                'description': 'Shell command to execute'
                            },
                            'container': {
                                'type': 'string',
                                'description': 'Container to execute in (frontend, backend, database, services)',
                                'enum': ['frontend', 'backend', 'database', 'services']
                            }
                        },
                        'required': ['command']
                    },
                    'workspace_tool': True,
                    'timeout_seconds': 60,
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f"Created execute-command tool for project: {project.name}")
            else:
                self.stdout.write(f"Tool already exists for project: {project.name}")
        
        self.stdout.write(self.style.SUCCESS(f"Created {created_count} new execute-command tools"))