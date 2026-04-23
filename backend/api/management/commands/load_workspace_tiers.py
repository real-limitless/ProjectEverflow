"""
Management command to load default workspace resource tiers.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import WorkspaceResourceTier

User = get_user_model()


class Command(BaseCommand):
    help = 'Load default workspace resource tiers (t-shirt sizing)'

    def handle(self, *args, **options):
        self.stdout.write('Loading workspace resource tiers...')
        
        # Get or create a system admin user for tier creation
        admin_user, _ = User.objects.get_or_create(
            username='system',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        
        tiers = [
            {
                'name': 'Light',
                'slug': 'light',
                'cpu_limit': '1.0',
                'memory_limit': '2g',
                'is_default': False,
            },
            {
                'name': 'Standard',
                'slug': 'standard',
                'cpu_limit': '2.0',
                'memory_limit': '4g',
                'is_default': True,
            },
            {
                'name': 'Heavy',
                'slug': 'heavy',
                'cpu_limit': '4.0',
                'memory_limit': '8g',
                'is_default': False,
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for tier_data in tiers:
            tier, created = WorkspaceResourceTier.objects.update_or_create(
                slug=tier_data['slug'],
                defaults={
                    'name': tier_data['name'],
                    'cpu_limit': tier_data['cpu_limit'],
                    'memory_limit': tier_data['memory_limit'],
                    'is_default': tier_data['is_default'],
                    'is_active': True,
                    'created_by': admin_user,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Created tier: {tier.name} ({tier.cpu_limit} CPU, {tier.memory_limit} RAM)'
                ))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(
                    f'  ↻ Updated tier: {tier.name} ({tier.cpu_limit} CPU, {tier.memory_limit} RAM)'
                ))
        
        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted: {created_count} created, {updated_count} updated'
        ))
