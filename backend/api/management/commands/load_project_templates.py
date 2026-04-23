from django.core.management.base import BaseCommand
from api.models import ProjectTemplate

class Command(BaseCommand):
    help = 'Load initial project templates'

    def handle(self, *args, **options):
        templates = [
            {
                'name': 'React AI Chatbot',
                'description': 'A modern chatbot interface built with React and TypeScript',
                'language': 'TypeScript',
                'framework': 'React',
                'difficulty': 'intermediate',
                'tags': ['React', 'TypeScript', 'AI', 'Chat'],
            },
            {
                'name': 'Django REST API',
                'description': 'RESTful API backend with authentication and database',
                'language': 'Python',
                'framework': 'Django',
                'difficulty': 'intermediate',
                'tags': ['Django', 'Python', 'API', 'REST'],
            },
            {
                'name': 'FastAPI ML Service',
                'description': 'Machine learning API with FastAPI and scikit-learn',
                'language': 'Python',
                'framework': 'FastAPI',
                'difficulty': 'advanced',
                'tags': ['FastAPI', 'Python', 'ML', 'API'],
            },
            {
                'name': 'Next.js Analytics Dashboard',
                'description': 'Full-stack dashboard with Next.js and PostgreSQL',
                'language': 'TypeScript',
                'framework': 'Next.js',
                'difficulty': 'intermediate',
                'tags': ['Next.js', 'React', 'Dashboard', 'Analytics'],
            },
            {
                'name': 'Express.js Backend',
                'description': 'Node.js backend with Express and MongoDB',
                'language': 'JavaScript',
                'framework': 'Express',
                'difficulty': 'beginner',
                'tags': ['Express', 'Node.js', 'API', 'MongoDB'],
            },
            {
                'name': 'Vue.js Admin Panel',
                'description': 'Admin dashboard built with Vue 3 and Composition API',
                'language': 'TypeScript',
                'framework': 'Vue',
                'difficulty': 'intermediate',
                'tags': ['Vue', 'Dashboard', 'Admin', 'TypeScript'],
            },
        ]

        for template_data in templates:
            template, created = ProjectTemplate.objects.get_or_create(
                name=template_data['name'],
                defaults=template_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully created template "{template.name}"')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Template "{template.name}" already exists')
                )

        self.stdout.write(
            self.style.SUCCESS('Project templates loading completed!')
        )