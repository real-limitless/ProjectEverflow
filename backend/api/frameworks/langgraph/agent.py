"""
LangGraph Deep Agent implementation (Supervisor Architecture).
"""
import asyncio
import operator
from typing import Dict, List, Any, Sequence, TypedDict, Annotated, Union, AsyncGenerator
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, FunctionMessage

from api.models import ChatSession, ProjectTool
from .adapter import CustomChatModel
from .workers import create_coder_worker, create_tool_runner_worker
from .supervisor import create_supervisor_chain
from .adapters import get_project_tools_definitions

# Define the agent state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    next: str

def create_agent(session: ChatSession, container_name: str):
    """
    Create a LangGraph Deep Agent (Supervisor + Workers) for the given session.
    """

    # 1. Resolve LLM Provider
    from api.views import ChatSessionViewSet
    viewset = ChatSessionViewSet()
    provider = viewset._resolve_provider_hierarchy(session)

    if not provider:
        raise ValueError("No LLM provider available for session")

    # 2. Resolve Container Name
    actual_container_name = container_name
    try:
        from api.podman_manager import PodmanManager
        manager = PodmanManager(session.project)
        found_container = manager._get_workspace_container_name()
        if found_container:
            actual_container_name = found_container
    except Exception:
        pass

    # 3. Initialize Shared LLM
    llm = CustomChatModel(provider, session)
    
    # 4. Resolve Custom Tools
    # Note: accessing M2M field session.enabled_tools
    try:
        enabled_tool_ids = list(session.enabled_tools.values_list('id', flat=True))
    except Exception:
        enabled_tool_ids = []
        
    custom_tools = get_project_tools_definitions(session.project, enabled_tool_ids)
    
    # 5. Define Workers
    members = ["Coder"]
    if custom_tools:
        members.append("ToolRunner")
    
    # Create Workers
    coder_agent = create_coder_worker(llm, session.project, actual_container_name)
    
    # Helper for Coder Node
    async def invoke_coder(state):
        try:
            response = await coder_agent.ainvoke(state)
            # We return the last message from the worker as the result
            return {"messages": [response["messages"][-1]]}
        except Exception as e:
            return {"messages": [AIMessage(content=f"Coder Worker Error: {str(e)}")]}

    async def invoke_tool_runner(state):
        try:
            tool_runner = create_tool_runner_worker(llm, custom_tools)
            response = await tool_runner.ainvoke(state)
            return {"messages": [response["messages"][-1]]}
        except Exception as e:
            return {"messages": [AIMessage(content=f"ToolRunner Error: {str(e)}")]}

    # 6. Create Supervisor
    supervisor_chain = create_supervisor_chain(llm, members)

    # 7. Build Graph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("Supervisor", supervisor_chain)
    workflow.add_node("Coder", invoke_coder)
    
    if custom_tools:
        workflow.add_node("ToolRunner", invoke_tool_runner)

    # 8. Define Edges
    workflow.add_edge(START, "Supervisor")
    
    # Map supervisor output to next node
    router_map = {name: name for name in members}
    router_map["FINISH"] = END
    
    workflow.add_conditional_edges(
        "Supervisor",
        lambda x: x["next"],
        router_map
    )
    
    # Workers always report back to supervisor
    workflow.add_edge("Coder", "Supervisor")
    
    if custom_tools:
        workflow.add_edge("ToolRunner", "Supervisor")

    # 9. Compile
    memory = InMemorySaver()
    return workflow.compile(checkpointer=memory)

async def run_agent_stream(
    graph, 
    user_input: str, 
    session_id: int, 
    max_iterations: int = 25
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Run the agent graph and yield events for the frontend.
    """
    from api.models import ChatSession, ChatMessage
    
    # helper for async ORM
    from asgiref.sync import sync_to_async
    
    # We use sync_to_async for DB access
    messages_qs = await sync_to_async(lambda: list(ChatMessage.objects.filter(session_id=session_id).order_by('created_at')))()
    
    existing_messages = []
    for msg in messages_qs:
        if msg.message_type == 'user':
            existing_messages.append(HumanMessage(content=msg.content))
        elif msg.message_type == 'assistant':
            existing_messages.append(AIMessage(content=msg.content))
            
    initial_messages = existing_messages + [HumanMessage(content=user_input)]

    config = {
        "configurable": {"thread_id": str(session_id)},
        "recursion_limit": max_iterations
    }

    yield {"type": "thinking", "content": "Agent is reasoning related to your request..."}
    
    iterations = 0
    final_content_parts = []
    
    try:
        async for step in graph.astream(
            {"messages": initial_messages},
            config=config
        ):
            iterations += 1
            node_name = list(step.keys())[0]
            state_update = step[node_name]
            
            if node_name == "Supervisor":
                next_node = state_update.get("next")
                if next_node and next_node != "FINISH":
                    yield {"type": "thinking", "content": f"Delegating task to {next_node}..."}
            
            elif node_name in ["Coder", "ToolRunner"]:
                msgs = state_update.get("messages", [])
                if msgs:
                    # In our wrap, msgs is a list containing typically one AIMessage
                    last_msg = msgs[-1]
                    content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
                    
                    if content:
                        final_content_parts.append(content)
                        # We treat worker output as a 'tool_end' kind of execution result for the UI, 
                        # or just distinct thinking block.
                        yield {"type": "thinking", "content": f"**{node_name} Output:**\n{content}"}

        # Combine all parts for the final answer
        full_response = "\n\n".join(final_content_parts)
        if not full_response:
            full_response = "Task completed (no textual output)."
            
        yield {
            "type": "final", 
            "content": full_response,
            "iterations": iterations,
            "tool_calls": [], # We don't have granular tool calls in this mode yet
        }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "error", "content": f"Agent execution failed: {str(e)}"}
