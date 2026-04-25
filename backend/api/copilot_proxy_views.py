"""
Copilot Mode Proxy Views

Proxies requests to the agent service running inside workspace containers.
Handles API key injection and authentication.
"""
import json
import logging
from typing import Optional

from django.http import StreamingHttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
import requests

from .models import Project, LLMProvider, ProjectPod, ProjectService
from .podman_orchestrator import PodmanOrchestrator

logger = logging.getLogger(__name__)


class CopilotProxyView(APIView):
    """Proxy requests to the copilot agent running in the workspace container"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_container_agent_url(self, project_id: int) -> Optional[str]:
        """Get the URL for the agent service in the project's container"""
        try:
            project = Project.objects.get(id=project_id)
            
            # Find the workspace service from DB to get the actual container name
            try:
                pod = ProjectPod.objects.get(project=project)
                workspace_service = ProjectService.objects.filter(
                    pod=pod, service_type='ai-workspace'
                ).first()
                
                if workspace_service and workspace_service.container_name:
                    container_name = workspace_service.container_name
                else:
                    # Fallback: generate the name using orchestrator convention
                    orchestrator = PodmanOrchestrator()
                    service_name = "workspace-shared" if project.workspace_mode != 'personal' else f"workspace-{project_id}"
                    container_name = orchestrator._generate_container_name(project_id, service_name)
            except ProjectPod.DoesNotExist:
                return None
            
            # Check if container is running
            orchestrator = PodmanOrchestrator()
            if not orchestrator._container_exists(container_name):
                logger.debug(f"Copilot container not found: {container_name}")
                return None
            
            # Get container IP
            result = orchestrator._run([
                'inspect', container_name,
                '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
            ])
            
            if result.returncode == 0 and result.stdout.strip():
                ip = result.stdout.strip()
                return f"http://{ip}:8080"
            
            return None
        except Exception as e:
            logger.error(f"Failed to get container agent URL: {e}")
            return None
    
    def get_api_credentials(self, project: Project, user) -> dict:
        """Get API credentials to inject into the agent"""
        credentials = {}
        
        # Try to get from project's default provider
        if project.default_llm_provider:
            provider = project.default_llm_provider
            credentials['LLM_API_KEY'] = provider.get_api_key()
            credentials['LLM_BASE_URL'] = provider.base_url
            if provider.available_models:
                credentials['LLM_MODEL'] = provider.available_models[0]['id']
            return credentials
        
        # Try user's default provider
        if hasattr(user, 'default_llm_provider') and user.default_llm_provider:
            provider = user.default_llm_provider
            credentials['LLM_API_KEY'] = provider.get_api_key()
            credentials['LLM_BASE_URL'] = provider.base_url
            if provider.available_models:
                credentials['LLM_MODEL'] = provider.available_models[0]['id']
            return credentials
        
        # Try first active provider
        provider = LLMProvider.objects.filter(is_active=True).first()
        if provider:
            credentials['LLM_API_KEY'] = provider.get_api_key()
            credentials['LLM_BASE_URL'] = provider.base_url
            if provider.available_models:
                credentials['LLM_MODEL'] = provider.available_models[0]['id']
        
        return credentials
    
    def post(self, request, project_id, endpoint='chat'):
        """Handle POST requests to copilot endpoints"""
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=404)
        
        # Get agent URL
        agent_url = self.get_container_agent_url(project_id)
        if not agent_url:
            return Response({
                'error': 'Copilot agent not available',
                'detail': 'Ensure the workspace is running with COPILOT_MODE=true'
            }, status=503)
        
        # Get API credentials
        credentials = self.get_api_credentials(project, request.user)
        
        if endpoint == 'chat/stream':
            return self._proxy_stream(agent_url, endpoint, request.data, credentials)
        else:
            return self._proxy_request(agent_url, endpoint, request.data, credentials)
    
    def get(self, request, project_id, endpoint='health'):
        """Handle GET requests to copilot endpoints"""
        agent_url = self.get_container_agent_url(project_id)
        if not agent_url:
            return Response({
                'error': 'Copilot agent not available',
                'detail': 'Ensure the workspace is running with COPILOT_MODE=true'
            }, status=503)
        
        try:
            response = requests.get(f"{agent_url}/{endpoint}", timeout=10)
            return Response(response.json(), status=response.status_code)
        except requests.exceptions.ConnectionError:
            logger.warning(f"Copilot agent not reachable at {agent_url}/{endpoint}")
            return Response({
                'error': 'Copilot agent not reachable',
                'detail': 'The workspace container is running but the agent service on port 8080 is not responding. '
                          'Ensure the container image includes the agent service and COPILOT_MODE=true is set.'
            }, status=503)
        except Exception as e:
            logger.error(f"Copilot proxy GET error: {e}")
            return Response({'error': str(e)}, status=502)
    
    def _proxy_request(self, agent_url: str, endpoint: str, data: dict, credentials: dict):
        """Proxy a non-streaming request"""
        try:
            # Inject credentials into request headers
            headers = {
                'Content-Type': 'application/json',
            }
            for key, value in credentials.items():
                headers[f'X-Agent-{key}'] = value
            
            response = requests.post(
                f"{agent_url}/{endpoint}",
                json=data,
                headers=headers,
                timeout=120
            )
            
            return Response(response.json(), status=response.status_code)
        except Exception as e:
            logger.error(f"Copilot proxy error: {e}")
            return Response({'error': str(e)}, status=500)
    
    def _proxy_stream(self, agent_url: str, endpoint: str, data: dict, credentials: dict):
        """Proxy a streaming SSE request"""
        
        def event_generator():
            try:
                headers = {
                    'Content-Type': 'application/json',
                }
                for key, value in credentials.items():
                    headers[f'X-Agent-{key}'] = value
                
                with requests.post(
                    f"{agent_url}/{endpoint}",
                    json=data,
                    headers=headers,
                    stream=True,
                    timeout=120
                ) as response:
                    if response.status_code != 200:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Agent error: {response.status_code}'})}\n\n"
                        return
                    
                    for line in response.iter_lines(decode_unicode=True):
                        if line:
                            yield f"{line}\n\n"
                
            except requests.exceptions.Timeout:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out'})}\n\n"
            except Exception as e:
                logger.error(f"Copilot stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return StreamingHttpResponse(
            event_generator(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )


# View instances for URL routing
copilot_health_view = CopilotProxyView.as_view()
copilot_tools_view = CopilotProxyView.as_view()
copilot_chat_view = CopilotProxyView.as_view()
copilot_chat_stream_view = CopilotProxyView.as_view()
