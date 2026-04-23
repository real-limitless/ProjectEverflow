"""
LLM Configuration Views
API endpoints for managing LLM configurations
"""

from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from .llm_config import get_llm_manager


class LLMConfigViewSet(viewsets.ViewSet):
    """ViewSet for LLM configuration management"""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def available_llms(self, request):
        """Get list of available LLMs"""
        llm_manager = get_llm_manager()
        available_llms = llm_manager.get_enabled_llms()

        # Convert to dict format for API response
        llms_data = []
        for llm in available_llms:
            llms_data.append({
                'id': llm.id,
                'name': llm.name,
                'provider': llm.provider,
                'model': llm.model,
                'description': llm.description,
                'max_tokens': llm.max_tokens,
                'temperature': llm.temperature,
                'available': llm_manager.is_llm_available(llm.id)
            })

        return Response({
            'llms': llms_data,
            'default_llm': llm_manager.get_llm_config().id
        })