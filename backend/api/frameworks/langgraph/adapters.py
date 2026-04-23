from typing import List, Any
from langchain_core.tools import StructuredTool
from api.models import ProjectTool, Project
from api.podman_manager import PodmanManager

def convert_project_tool_to_langchain(tool: ProjectTool, project: Project) -> StructuredTool:
    """
    Converts a Django ProjectTool model into a LangChain StructuredTool
    that executes via PodmanManager.
    """
    
    def tool_function(**kwargs) -> str:
        manager = PodmanManager(project)
        # Execute the tool using the manager
        # tool.slug identifies the tool
        # kwargs become the payload
        try:
            result = manager.run_tool(tool, kwargs)
            
            output = []
            if isinstance(result, dict):
                if result.get('stdout'):
                    output.append(f"STDOUT:\n{result['stdout']}")
                if result.get('stderr'):
                    output.append(f"STDERR:\n{result['stderr']}")
                if result.get('error'):
                    output.append(f"ERROR:\n{result['error']}")
            else:
                output.append(str(result))
                
            return "\n".join(output) if output else "Tool executed successfully with no output."
        except Exception as e:
            return f"Error executing tool {tool.name}: {str(e)}"

    return StructuredTool.from_function(
        func=tool_function,
        name=tool.slug.replace('-', '_'),  # Ensure valid python identifier for tool name
        description=tool.description or f"Executes {tool.name}",
    )

def get_project_tools_definitions(project: Project, tool_ids: List[int]) -> List[StructuredTool]:
    """Retrieve ProjectTools by ID and convert them to LangChain definitions."""
    if not tool_ids:
        return []
    
    tools = ProjectTool.objects.filter(id__in=tool_ids, project=project, is_active=True)
    return [convert_project_tool_to_langchain(t, project) for t in tools]
