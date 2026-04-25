from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent
from .tools import get_workspace_tools

def create_coder_worker(model, project, container_name):
    """
    Creates a worker specialized in coding tasks (file system, shell).
    """
    # Standard workspace tools (fs, shell)
    tools = get_workspace_tools(project, container_name)
    
    system_message = SystemMessage(content="""You are a Coder worker. 
    Your job is to modify files, run shell commands, and explore the codebase.
    You have access to the file system and terminal.
    
    When asked to read a file, always provide the full path.
    When asked to edit a file, always check if it exists first unless you are creating it.
    """)
    
    return create_react_agent(model, tools, prompt=system_message)

def create_tool_runner_worker(model, tools):
    """
    Creates a worker specialized in running custom project tools.
    """
    system_message = SystemMessage(content="""You are a Tool Runner.
    You have access to specialized tools defined for this project.
    Execute them as requested by the supervisor.
    
    If a tool requires arguments that you don't have, ask for clarification.
    Report the tool output back exactly as received.
    """)
    
    return create_react_agent(model, tools, prompt=system_message)
