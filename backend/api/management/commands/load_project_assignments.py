from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Project, ComplianceTemplate, ProjectAssignment, User

class Command(BaseCommand):
    help = 'Load test project assignment data'

    def handle(self, *args, **options):
        # Get or create some projects
        projects = list(Project.objects.all()[:3])  # Get first 3 projects
        
        # If no projects exist, create some test projects
        if not projects:
            # Get the first user as owner
            try:
                owner = User.objects.first()
                if not owner:
                    self.stdout.write(self.style.ERROR('No users found. Please create a user first.'))
                    return
                
                test_projects = [
                    {'name': 'AI Document Analyzer', 'description': 'AI-powered document analysis tool'},
                    {'name': 'Smart Code Review', 'description': 'Automated code review assistant'},
                    {'name': 'Data Visualization Dashboard', 'description': 'Interactive data visualization platform'},
                ]
                
                for project_data in test_projects:
                    project, created = Project.objects.get_or_create(
                        name=project_data['name'],
                        defaults={
                            'description': project_data['description'],
                            'owner': owner,
                            'status': 'in_development',
                            'progress': 50,
                        }
                    )
                    if created:
                        # Add owner as contributor
                        project.contributors.add(owner)
                        self.stdout.write(f'Created test project: {project.name}')
                    projects.append(project)
                    
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR('No users found. Please create a user first.'))
                return

        templates = ComplianceTemplate.objects.all()[:2]  # Get first 2 templates

        if not templates:
            self.stdout.write(self.style.WARNING('No compliance templates found. Please run load_compliance_data first.'))
            return

        # Create some test assignments
        assignments_created = 0
        for i, project in enumerate(projects):
            # Assign a template to some projects
            if i < len(templates):
                template = templates[i]
                assignment, created = ProjectAssignment.objects.get_or_create(
                    project=project,
                    template=template,
                    defaults={
                        'status': 'not_run',
                        'violations': 0
                    }
                )
                if created:
                    assignments_created += 1
                    self.stdout.write(f'Created assignment: {project.name} -> {template.name}')

            # Create an assignment without template for some projects
            if i == 0:  # Only for first project
                assignment, created = ProjectAssignment.objects.get_or_create(
                    project=project,
                    template=None,
                    defaults={
                        'status': 'pass',
                        'violations': 0
                    }
                )
                if created:
                    assignments_created += 1
                    self.stdout.write(f'Created assignment: {project.name} -> No template')

        self.stdout.write(self.style.SUCCESS(f'Successfully created {assignments_created} project assignments'))