"""
Django management command to test LangGraph agent.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import Project, ChatSession
from api.frameworks.langgraph import create_agent, run_agent_stream
import asyncio

User = get_user_model()


class Command(BaseCommand):
    help = 'Test LangGraph agent outside UI'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, required=True, help='Project ID')
        parser.add_argument('--user', type=str, default='admin', help='Username')
        parser.add_argument('--message', type=str, required=True, help='User message')
        parser.add_argument('--max-iterations', type=int, default=10, help='Max agent iterations')

    def handle(self, *args, **options):
        try:
            project = Project.objects.get(pk=options['project'])
            user = User.objects.get(username=options['user'])

            # Create or get session
            session, created = ChatSession.objects.get_or_create(
                user=user,
                project=project,
                mode='agent',
                defaults={'title': f'CLI Test Session for {project.name}'}
            )

            if created:
                self.stdout.write(f"Created new session: {session.id}")
            else:
                self.stdout.write(f"Using existing session: {session.id}")

            # Get container name (use same logic as web interface)
            container_name = f"proj-pod-{project.id}-workspace-shared"

            # Create agent
            graph = create_agent(session, container_name)

            # Run agent
            async def run():
                iteration = 0
                async for event in run_agent_stream(graph, options['message'], session.id, options['max_iterations']):
                    iteration += 1
                    self.stdout.write(f"[Iteration {iteration}] {event['type']}: {event.get('content', 'N/A')[:100]}...")
                    
                    if event['type'] == 'thinking':
                        self.stdout.write(self.style.WARNING(f"[Thinking] {event['content']}"))
                    elif event['type'] == 'tool_start':
                        self.stdout.write(self.style.HTTP_INFO(f"[Tool Start] {event['name']} with args: {event.get('args', {})}"))
                    elif event['type'] == 'tool_end':
                        self.stdout.write(self.style.SUCCESS(f"[Tool End] Result: {event['output'][:200]}..."))
                    elif event['type'] == 'todos_update':
                        self.stdout.write(self.style.NOTICE(f"[Todos Update] {len(event['todos'])} todos"))
                    elif event['type'] == 'final':
                        self.stdout.write(self.style.HTTP_SUCCESS(f"\n[Final Answer]\n{event['content']}"))
                    elif event['type'] == 'error':
                        self.stdout.write(self.style.ERROR(f"[Error] {event['content']}"))

            try:
                asyncio.run(asyncio.wait_for(run(), timeout=60.0))  # 60 second timeout
            except asyncio.TimeoutError:
                self.stderr.write("Agent execution timed out after 60 seconds")
            except Exception as e:
                self.stderr.write(f"Agent execution failed: {str(e)}")
                import traceback
                traceback.print_exc()

        except Project.DoesNotExist:
            self.stderr.write(f"Project {options['project']} does not exist")
        except User.DoesNotExist:
            self.stderr.write(f"User {options['user']} does not exist")
        except Exception as e:
            self.stderr.write(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()