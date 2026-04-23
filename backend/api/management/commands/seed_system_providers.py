"""
Management command to seed system-level LLM providers from environment variables.
Migrates .env configuration to LLMProvider records for the new multi-level provider system.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import LLMProvider
import os
import asyncio

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed system-level LLM providers from environment variables'

    def add_arguments(self, parser):
        parser.add_argument(
            '--discover',
            action='store_true',
            help='Automatically discover models from providers after seeding',
        )

    def handle(self, *args, **options):
        self.stdout.write('Seeding system-level LLM providers...')
        
        # Get or create a system admin user for provider creation
        admin_user, _ = User.objects.get_or_create(
            username='system',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        
        providers_to_seed = []
        
        # OpenAI
        openai_key = os.getenv('OPENAI_API_KEY')
        openai_base = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        if openai_key:
            providers_to_seed.append({
                'provider_type': 'openai',
                'instance_name': 'System OpenAI',
                'api_key_plain': openai_key,
                'base_url': openai_base,
            })
        
        # Anthropic
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        anthropic_base = os.getenv('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
        if anthropic_key:
            providers_to_seed.append({
                'provider_type': 'anthropic',
                'instance_name': 'System Anthropic',
                'api_key_plain': anthropic_key,
                'base_url': anthropic_base,
            })
        
        # OpenRouter (if exists in env)
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if openrouter_key:
            providers_to_seed.append({
                'provider_type': 'openrouter',
                'instance_name': 'System OpenRouter',
                'api_key_plain': openrouter_key,
                'base_url': 'https://openrouter.ai/api/v1',
            })
        
        # Ollama (local, no API key)
        ollama_base = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        providers_to_seed.append({
            'provider_type': 'ollama',
            'instance_name': 'System Ollama',
            'api_key_plain': '',
            'base_url': ollama_base,
        })
        
        # LiteMaaS (if exists in env)
        litemaas_key = os.getenv('LITEMAAS_API_KEY')
        litemaas_base = os.getenv('LITEMAAS_BASE_URL')
        if litemaas_key and litemaas_base:
            providers_to_seed.append({
                'provider_type': 'litemaas',
                'instance_name': 'System LiteMaaS',
                'api_key_plain': litemaas_key,
                'base_url': litemaas_base,
            })
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for provider_data in providers_to_seed:
            # Check if provider already exists
            existing = LLMProvider.objects.filter(
                scope='system',
                provider_type=provider_data['provider_type'],
                instance_name=provider_data['instance_name']
            ).first()
            
            if existing:
                # Update existing provider
                if provider_data.get('api_key_plain'):
                    existing.set_api_key(provider_data['api_key_plain'])
                existing.base_url = provider_data.get('base_url', '')
                existing.is_active = True
                existing.save()
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Updated: {provider_data['instance_name']}")
                )
            else:
                # Create new provider
                try:
                    provider = LLMProvider.objects.create(
                        scope='system',
                        provider_type=provider_data['provider_type'],
                        instance_name=provider_data['instance_name'],
                        base_url=provider_data.get('base_url', ''),
                        is_active=True,
                        created_by=admin_user
                    )
                    
                    # Set API key if provided
                    if provider_data.get('api_key_plain'):
                        provider.set_api_key(provider_data['api_key_plain'])
                        provider.save()
                    
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  + Created: {provider_data['instance_name']}")
                    )
                except Exception as e:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Failed to create {provider_data['instance_name']}: {str(e)}")
                    )
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_count} created, {updated_count} updated, {skipped_count} skipped'
            )
        )
        
        # Run model discovery if requested
        if options['discover']:
            self.stdout.write('')
            self.stdout.write('Discovering models for all system providers...')
            
            from api.llm_discovery import LLMDiscoveryService
            from datetime import datetime
            
            system_providers = LLMProvider.objects.filter(scope='system', is_active=True)
            
            for provider in system_providers:
                try:
                    self.stdout.write(f'  Discovering models for {provider.instance_name}...')
                    api_key = provider.get_api_key() if provider.api_key else None
                    
                    models = asyncio.run(LLMDiscoveryService.discover_models(
                        provider.provider_type,
                        api_key,
                        provider.base_url
                    ))
                    
                    provider.available_models = models
                    provider.last_discovery = datetime.now()
                    provider.save()
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"    ✓ Found {len(models)} models")
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"    ⚠ Discovery failed: {str(e)}")
                    )
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Model discovery complete!'))
