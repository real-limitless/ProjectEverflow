import json
import os
from django.core.management.base import BaseCommand
from api.models import ComplianceCheck, ComplianceTemplate

class Command(BaseCommand):
    help = 'Load compliance check and template data from JSON files'

    def handle(self, *args, **options):
        # Load compliance checks
        json_path = os.path.join(os.path.dirname(__file__), '../../../../src/data/complianceChecks.json')
        with open(json_path, 'r') as f:
            data = json.load(f)

        # Load compliance checks
        check_id_to_name = {}
        checks_created = 0
        for check_data in data.get('checks', []):
            check, created = ComplianceCheck.objects.get_or_create(
                name=check_data['name'],
                defaults={
                    'description': check_data['description'],
                    'category': check_data['category'],
                    'severity': check_data['severity'].lower(),
                    'ai_prompt': check_data['aiPrompt'],
                    'is_active': check_data.get('enabled', True),
                }
            )
            if created:
                checks_created += 1
                self.stdout.write(f'Created check: {check.name}')
            
            # Store mapping from ID to name
            check_id_to_name[check_data['id']] = check_data['name']

        # Load compliance templates
        templates_created = 0
        for template_data in data.get('templates', []):
            template, created = ComplianceTemplate.objects.get_or_create(
                name=template_data['name'],
                defaults={
                    'description': template_data['description'],
                    'is_active': True,
                }
            )
            if created:
                # Add checks to template
                check_ids = template_data.get('checks', [])
                for check_id in check_ids:
                    check_name = check_id_to_name.get(check_id)
                    if check_name:
                        try:
                            check = ComplianceCheck.objects.get(name=check_name)
                            template.checks.add(check)
                        except ComplianceCheck.DoesNotExist:
                            self.stdout.write(self.style.WARNING(f'Check not found: {check_name}'))

                template.save()
                templates_created += 1
                self.stdout.write(f'Created template: {template.name}')

        self.stdout.write(self.style.SUCCESS(f'Successfully created {checks_created} compliance checks and {templates_created} templates'))