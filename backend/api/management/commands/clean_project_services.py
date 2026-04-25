from django.core.management.base import BaseCommand
from api.models import ProjectService, ProjectPod


class Command(BaseCommand):
    help = 'Clean up project services and pods for a specific project'

    def add_arguments(self, parser):
        parser.add_argument('project_id', type=int, help='Project ID to clean')

    def handle(self, *args, **options):
        project_id = options['project_id']
        
        try:
            # Delete services
            services = ProjectService.objects.filter(pod__project_id=project_id)
            service_count = services.count()
            services.delete()
            
            # Delete pods
            pods = ProjectPod.objects.filter(project_id=project_id)
            pod_count = pods.count()
            pods.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully cleaned project {project_id}: '
                    f'{service_count} services, {pod_count} pods'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning project {project_id}: {str(e)}')
            )
