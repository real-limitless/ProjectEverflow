from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChatMessage


class ChatMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat messages"""
    queryset = ChatMessage.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['put'])
    def update_message(self, request, pk=None):
        """Update a chat message content"""
        try:
            message = self.get_object()
            new_content = request.data.get('content')
            
            if not new_content:
                return Response({'error': 'Content is required'}, status=400)
            
            # Check if user owns this message's session
            if message.session.created_by != request.user:
                return Response({'error': 'Unauthorized'}, status=403)
            
            # Update message
            message.content = new_content
            message.save()
            
            # Optionally delete all messages after this one (if requested)
            if request.data.get('clear_after', False):
                ChatMessage.objects.filter(
                    session=message.session,
                    created_at__gt=message.created_at
                ).delete()
            
            return Response({
                'id': message.id,
                'content': message.content,
                'updated_at': message.created_at  # or use an updated_at field if available
            }, status=200)
        except ChatMessage.DoesNotExist:
            return Response({'error': 'Message not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=500)
