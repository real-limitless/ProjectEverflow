"""
LLM Cost Calculator Service

Handles cost calculation and aggregation for LLM usage reporting and billing.
Calculates costs based on token usage and provider pricing data.
"""

from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate
import logging

logger = logging.getLogger(__name__)


class CostCalculator:
    """Service for calculating and aggregating LLM usage costs"""
    
    @staticmethod
    def calculate_message_cost(prompt_tokens: int, completion_tokens: int, pricing: Dict) -> Decimal:
        """
        Calculate cost for a single message
        
        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            pricing: Dict with 'prompt' and 'completion' prices per 1M tokens
            
        Returns:
            Decimal cost in USD
        """
        if not pricing or not prompt_tokens or not completion_tokens:
            return Decimal('0.000000')
        
        prompt_cost = Decimal(str(prompt_tokens)) * Decimal(str(pricing.get('prompt', 0))) / Decimal('1000000')
        completion_cost = Decimal(str(completion_tokens)) * Decimal(str(pricing.get('completion', 0))) / Decimal('1000000')
        
        return (prompt_cost + completion_cost).quantize(Decimal('0.000001'))
    
    @staticmethod
    def get_model_pricing(provider, model_id: str) -> Optional[Dict]:
        """
        Extract pricing for a specific model from provider's available_models
        
        Args:
            provider: LLMProvider instance
            model_id: Model identifier
            
        Returns:
            Dict with 'prompt' and 'completion' prices, or None if not found
        """
        if not provider or not provider.available_models:
            return None
        
        for model in provider.available_models:
            if model.get('id') == model_id:
                return model.get('pricing', {})
        
        return None
    
    @staticmethod
    def calculate_and_update_message_cost(message, provider, model_id: str):
        """
        Calculate cost for a message and update the estimated_cost field
        
        Args:
            message: ChatMessage instance
            provider: LLMProvider instance
            model_id: Model identifier used
        """
        if not message.prompt_tokens or not message.completion_tokens:
            return
        
        pricing = CostCalculator.get_model_pricing(provider, model_id)
        if not pricing:
            logger.warning(f"No pricing found for model {model_id} in provider {provider.id}")
            return
        
        cost = CostCalculator.calculate_message_cost(
            message.prompt_tokens,
            message.completion_tokens,
            pricing
        )
        message.estimated_cost = cost
        message.save(update_fields=['estimated_cost'])
    
    @staticmethod
    def get_provider_usage_stats(provider_id: int, start_date: Optional[datetime] = None, 
                                 end_date: Optional[datetime] = None) -> Dict:
        """
        Get usage statistics for a specific provider
        
        Args:
            provider_id: LLMProvider ID
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Dict with usage statistics
        """
        from api.models import ChatMessage
        
        queryset = ChatMessage.objects.filter(used_by_provider_id=provider_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_messages=Count('id'),
            total_prompt_tokens=Sum('prompt_tokens'),
            total_completion_tokens=Sum('completion_tokens'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('estimated_cost')
        )
        
        return {
            'total_messages': stats['total_messages'] or 0,
            'total_prompt_tokens': stats['total_prompt_tokens'] or 0,
            'total_completion_tokens': stats['total_completion_tokens'] or 0,
            'total_tokens': stats['total_tokens'] or 0,
            'total_cost': float(stats['total_cost'] or 0),
        }
    
    @staticmethod
    def get_scope_usage_stats(scope: str, scope_id: Optional[int] = None,
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None) -> Dict:
        """
        Get usage statistics for a specific scope (system/team/project/user)
        
        Args:
            scope: Scope type ('system', 'team', 'project', 'user')
            scope_id: ID of the team/project/user (None for system)
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Dict with aggregated usage statistics
        """
        from api.models import ChatMessage, LLMProvider
        
        # Build provider filter based on scope
        provider_filter = Q(used_by_provider__scope=scope)
        
        if scope == 'team' and scope_id:
            provider_filter &= Q(used_by_provider__scope_team_id=scope_id)
        elif scope == 'project' and scope_id:
            provider_filter &= Q(used_by_provider__scope_project_id=scope_id)
        elif scope == 'user' and scope_id:
            provider_filter &= Q(used_by_provider__scope_user_id=scope_id)
        
        queryset = ChatMessage.objects.filter(provider_filter)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_messages=Count('id'),
            total_prompt_tokens=Sum('prompt_tokens'),
            total_completion_tokens=Sum('completion_tokens'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('estimated_cost')
        )
        
        # Get per-provider breakdown
        provider_breakdown = queryset.values(
            'used_by_provider_id',
            'used_by_provider__instance_name',
            'used_by_provider__provider_type'
        ).annotate(
            messages=Count('id'),
            prompt_tokens=Sum('prompt_tokens'),
            completion_tokens=Sum('completion_tokens'),
            total_tokens=Sum('total_tokens'),
            cost=Sum('estimated_cost')
        ).order_by('-cost')
        
        return {
            'scope': scope,
            'scope_id': scope_id,
            'total_messages': stats['total_messages'] or 0,
            'total_prompt_tokens': stats['total_prompt_tokens'] or 0,
            'total_completion_tokens': stats['total_completion_tokens'] or 0,
            'total_tokens': stats['total_tokens'] or 0,
            'total_cost': float(stats['total_cost'] or 0),
            'provider_breakdown': [
                {
                    'provider_id': p['used_by_provider_id'],
                    'provider_name': p['used_by_provider__instance_name'],
                    'provider_type': p['used_by_provider__provider_type'],
                    'messages': p['messages'],
                    'prompt_tokens': p['prompt_tokens'] or 0,
                    'completion_tokens': p['completion_tokens'] or 0,
                    'total_tokens': p['total_tokens'] or 0,
                    'cost': float(p['cost'] or 0),
                }
                for p in provider_breakdown
            ]
        }
    
    @staticmethod
    def get_daily_usage_trends(scope: str, scope_id: Optional[int] = None,
                               days: int = 30) -> List[Dict]:
        """
        Get daily usage trends for charting
        
        Args:
            scope: Scope type
            scope_id: Optional scope ID
            days: Number of days to include
            
        Returns:
            List of daily statistics
        """
        from api.models import ChatMessage
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Build provider filter
        provider_filter = Q(used_by_provider__scope=scope)
        if scope == 'team' and scope_id:
            provider_filter &= Q(used_by_provider__scope_team_id=scope_id)
        elif scope == 'project' and scope_id:
            provider_filter &= Q(used_by_provider__scope_project_id=scope_id)
        elif scope == 'user' and scope_id:
            provider_filter &= Q(used_by_provider__scope_user_id=scope_id)
        
        daily_stats = ChatMessage.objects.filter(
            provider_filter,
            created_at__gte=start_date
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            messages=Count('id'),
            tokens=Sum('total_tokens'),
            cost=Sum('estimated_cost')
        ).order_by('date')
        
        return [
            {
                'date': stat['date'].isoformat(),
                'messages': stat['messages'],
                'tokens': stat['tokens'] or 0,
                'cost': float(stat['cost'] or 0),
            }
            for stat in daily_stats
        ]
    
    @staticmethod
    def get_user_usage_stats(user_id: int, start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> Dict:
        """
        Get usage statistics for a specific user across all their sessions
        
        Args:
            user_id: User ID
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Dict with user usage statistics
        """
        from api.models import ChatMessage
        
        queryset = ChatMessage.objects.filter(session__user_id=user_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_messages=Count('id'),
            total_prompt_tokens=Sum('prompt_tokens'),
            total_completion_tokens=Sum('completion_tokens'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('estimated_cost')
        )
        
        # Get per-provider breakdown
        provider_breakdown = queryset.values(
            'used_by_provider_id',
            'used_by_provider__instance_name',
            'used_by_provider__provider_type',
            'used_by_provider__scope'
        ).annotate(
            messages=Count('id'),
            cost=Sum('estimated_cost')
        ).order_by('-cost')
        
        return {
            'user_id': user_id,
            'total_messages': stats['total_messages'] or 0,
            'total_prompt_tokens': stats['total_prompt_tokens'] or 0,
            'total_completion_tokens': stats['total_completion_tokens'] or 0,
            'total_tokens': stats['total_tokens'] or 0,
            'total_cost': float(stats['total_cost'] or 0),
            'provider_breakdown': [
                {
                    'provider_id': p['used_by_provider_id'],
                    'provider_name': p['used_by_provider__instance_name'],
                    'provider_type': p['used_by_provider__provider_type'],
                    'scope': p['used_by_provider__scope'],
                    'messages': p['messages'],
                    'cost': float(p['cost'] or 0),
                }
                for p in provider_breakdown if p['used_by_provider_id']
            ]
        }
