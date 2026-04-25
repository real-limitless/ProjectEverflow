"""
LLM Provider Model Discovery Service

Handles automatic model discovery and pricing extraction from various LLM providers.
Supports OpenRouter, OpenAI, Anthropic, vLLM, and custom providers.
"""

import aiohttp
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Known pricing for providers without discovery APIs (prices per 1M tokens in USD)
ANTHROPIC_PRICING = {
    'claude-3-5-sonnet-20241022': {'prompt': 3.00, 'completion': 15.00, 'context_length': 200000},
    'claude-3-5-haiku-20241022': {'prompt': 0.80, 'completion': 4.00, 'context_length': 200000},
    'claude-3-opus-20240229': {'prompt': 15.00, 'completion': 75.00, 'context_length': 200000},
    'claude-3-sonnet-20240229': {'prompt': 3.00, 'completion': 15.00, 'context_length': 200000},
    'claude-3-haiku-20240307': {'prompt': 0.25, 'completion': 1.25, 'context_length': 200000},
}

OPENAI_PRICING = {
    'gpt-4o': {'prompt': 2.50, 'completion': 10.00, 'context_length': 128000},
    'gpt-4o-mini': {'prompt': 0.150, 'completion': 0.600, 'context_length': 128000},
    'gpt-4-turbo': {'prompt': 10.00, 'completion': 30.00, 'context_length': 128000},
    'gpt-4-turbo-2024-04-09': {'prompt': 10.00, 'completion': 30.00, 'context_length': 128000},
    'gpt-4': {'prompt': 30.00, 'completion': 60.00, 'context_length': 8192},
    'gpt-4-32k': {'prompt': 60.00, 'completion': 120.00, 'context_length': 32768},
    'gpt-3.5-turbo': {'prompt': 0.50, 'completion': 1.50, 'context_length': 16385},
    'gpt-3.5-turbo-16k': {'prompt': 3.00, 'completion': 4.00, 'context_length': 16385},
}


class LLMDiscoveryService:
    """Service for discovering models and pricing from LLM providers"""
    
    @staticmethod
    async def discover_openrouter_models(api_key: str, base_url: Optional[str] = None) -> List[Dict]:
        """
        Discover models from OpenRouter API
        
        Args:
            api_key: OpenRouter API key
            base_url: Optional custom base URL (defaults to https://openrouter.ai/api/v1)
            
        Returns:
            List of model dicts with id, name, pricing, context_length
        """
        url = f"{base_url or 'https://openrouter.ai/api/v1'}/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"OpenRouter discovery failed: {response.status}")
                        return []
                    
                    data = await response.json()
                    models = []
                    
                    for model in data.get('data', []):
                        # OpenRouter returns pricing per 1M tokens
                        pricing_data = model.get('pricing', {})
                        models.append({
                            'id': model.get('id'),
                            'name': model.get('name', model.get('id')),
                            'description': model.get('description', ''),
                            'context_length': model.get('context_length', 8192),
                            'pricing': {
                                'prompt': float(pricing_data.get('prompt', '0')) * 1000000,  # Convert to per 1M tokens
                                'completion': float(pricing_data.get('completion', '0')) * 1000000,
                            },
                            'provider': 'openrouter',
                        })
                    
                    logger.info(f"Discovered {len(models)} models from OpenRouter")
                    return models
                    
        except asyncio.TimeoutError:
            logger.error("OpenRouter discovery timed out")
            return []
        except Exception as e:
            logger.error(f"Error discovering OpenRouter models: {str(e)}")
            return []
    
    @staticmethod
    async def discover_openai_models(api_key: str, base_url: Optional[str] = None) -> List[Dict]:
        """
        Discover models from OpenAI API
        
        Args:
            api_key: OpenAI API key
            base_url: Optional custom base URL (defaults to https://api.openai.com/v1)
            
        Returns:
            List of model dicts with id, name, pricing, context_length
        """
        url = f"{base_url or 'https://api.openai.com/v1'}/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"OpenAI discovery failed: {response.status}")
                        return []
                    
                    data = await response.json()
                    models = []
                    
                    for model in data.get('data', []):
                        model_id = model.get('id')
                        # Only include GPT models
                        if not model_id.startswith('gpt-'):
                            continue
                        
                        # Get pricing from known pricing table
                        pricing = OPENAI_PRICING.get(model_id, {'prompt': 0, 'completion': 0, 'context_length': 8192})
                        
                        models.append({
                            'id': model_id,
                            'name': model_id.upper().replace('-', ' '),
                            'description': f'OpenAI {model_id}',
                            'context_length': pricing.get('context_length', 8192),
                            'pricing': {
                                'prompt': pricing.get('prompt', 0),
                                'completion': pricing.get('completion', 0),
                            },
                            'provider': 'openai',
                        })
                    
                    logger.info(f"Discovered {len(models)} models from OpenAI")
                    return models
                    
        except asyncio.TimeoutError:
            logger.error("OpenAI discovery timed out")
            return []
        except Exception as e:
            logger.error(f"Error discovering OpenAI models: {str(e)}")
            return []
    
    @staticmethod
    async def discover_anthropic_models(api_key: str, base_url: Optional[str] = None) -> List[Dict]:
        """
        Discover models from Anthropic (uses static pricing table)
        
        Anthropic doesn't have a models endpoint, so we return the known Claude models.
        
        Args:
            api_key: Anthropic API key (used for validation)
            base_url: Optional custom base URL
            
        Returns:
            List of model dicts with id, name, pricing, context_length
        """
        # Anthropic doesn't have a models discovery API, return known models
        models = []
        
        for model_id, pricing_info in ANTHROPIC_PRICING.items():
            models.append({
                'id': model_id,
                'name': model_id.replace('-', ' ').title(),
                'description': f'Anthropic {model_id}',
                'context_length': pricing_info['context_length'],
                'pricing': {
                    'prompt': pricing_info['prompt'],
                    'completion': pricing_info['completion'],
                },
                'provider': 'anthropic',
            })
        
        logger.info(f"Returning {len(models)} known Anthropic models")
        return models
    
    @staticmethod
    async def discover_vllm_models(api_key: Optional[str], base_url: str) -> List[Dict]:
        """
        Discover models from vLLM OpenAI-compatible endpoint
        
        Args:
            api_key: Optional API key for vLLM instance
            base_url: vLLM base URL
            
        Returns:
            List of model dicts with id, name (no pricing for self-hosted)
        """
        url = f"{base_url.rstrip('/')}/v1/models"
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"vLLM discovery failed: {response.status}")
                        return []
                    
                    data = await response.json()
                    models = []
                    
                    for model in data.get('data', []):
                        models.append({
                            'id': model.get('id'),
                            'name': model.get('id'),
                            'description': 'Self-hosted vLLM model',
                            'context_length': 8192,  # Default, may vary
                            'pricing': {
                                'prompt': 0,  # Self-hosted, no per-token cost
                                'completion': 0,
                            },
                            'provider': 'vllm',
                        })
                    
                    logger.info(f"Discovered {len(models)} models from vLLM at {base_url}")
                    return models
                    
        except asyncio.TimeoutError:
            logger.error(f"vLLM discovery timed out for {base_url}")
            return []
        except Exception as e:
            logger.error(f"Error discovering vLLM models: {str(e)}")
            return []
    
    @staticmethod
    async def discover_ollama_models(base_url: Optional[str] = None) -> List[Dict]:
        """
        Discover models from Ollama (local models, no API key needed)
        
        Args:
            base_url: Ollama base URL (defaults to http://localhost:11434)
            
        Returns:
            List of model dicts with id, name (no pricing for local models)
        """
        url = f"{base_url or 'http://localhost:11434'}/api/tags"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"Ollama discovery failed: {response.status}")
                        return []
                    
                    data = await response.json()
                    models = []
                    
                    for model in data.get('models', []):
                        models.append({
                            'id': model.get('name'),
                            'name': model.get('name'),
                            'description': f"Local Ollama model - {model.get('size', 'unknown size')}",
                            'context_length': 8192,  # Default, varies by model
                            'pricing': {
                                'prompt': 0,  # Local, no cost
                                'completion': 0,
                            },
                            'provider': 'ollama',
                        })
                    
                    logger.info(f"Discovered {len(models)} models from Ollama")
                    return models
                    
        except asyncio.TimeoutError:
            logger.error("Ollama discovery timed out")
            return []
        except Exception as e:
            logger.error(f"Error discovering Ollama models: {str(e)}")
            return []
    
    @staticmethod
    async def discover_models(provider_type: str, api_key: Optional[str], base_url: Optional[str]) -> List[Dict]:
        """
        Main entry point for model discovery
        
        Args:
            provider_type: Type of provider (openrouter, openai, anthropic, vllm, ollama, etc.)
            api_key: API key for the provider
            base_url: Optional custom base URL
            
        Returns:
            List of discovered models with pricing
        """
        provider_type = provider_type.lower()
        
        if provider_type == 'openrouter':
            return await LLMDiscoveryService.discover_openrouter_models(api_key, base_url)
        elif provider_type == 'openai':
            return await LLMDiscoveryService.discover_openai_models(api_key, base_url)
        elif provider_type == 'anthropic':
            return await LLMDiscoveryService.discover_anthropic_models(api_key, base_url)
        elif provider_type == 'vllm':
            return await LLMDiscoveryService.discover_vllm_models(api_key, base_url)
        elif provider_type == 'ollama':
            return await LLMDiscoveryService.discover_ollama_models(base_url)
        elif provider_type in ['litemaas', 'custom']:
            # For custom providers, try OpenAI-compatible endpoint
            if base_url:
                return await LLMDiscoveryService.discover_vllm_models(api_key, base_url)
            else:
                logger.warning(f"Cannot discover models for {provider_type} without base_url")
                return []
        else:
            logger.warning(f"Unknown provider type: {provider_type}")
            return []
    
    @staticmethod
    async def test_connection(provider_type: str, api_key: Optional[str], base_url: Optional[str]) -> Dict:
        """
        Test connection to a provider
        
        Args:
            provider_type: Type of provider
            api_key: API key for the provider
            base_url: Optional custom base URL
            
        Returns:
            Dict with 'success' boolean and 'message' string
        """
        try:
            models = await LLMDiscoveryService.discover_models(provider_type, api_key, base_url)
            if models:
                return {
                    'success': True,
                    'message': f'Successfully connected to {provider_type}. Found {len(models)} models.',
                    'model_count': len(models)
                }
            else:
                return {
                    'success': False,
                    'message': f'Connected to {provider_type} but no models found or API key invalid.',
                    'model_count': 0
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection failed: {str(e)}',
                'model_count': 0
            }
