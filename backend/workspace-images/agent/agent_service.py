#!/usr/bin/env python3
"""
Copilot Mode Agent Service - Runs inside workspace containers

This service provides a native AI agent that operates entirely within the 
workspace container, with direct access to files and tools without needing
to execute commands through podman exec.

Features:
- Native file system access
- Custom tools from /workspace/.agent/tools/
- LangGraph-based agent execution
- Real-time streaming responses via SSE
"""
import os
import sys
import json
import asyncio
import importlib.util
from pathlib import Path
from typing import List, Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Workspace paths
WORKSPACE_ROOT = Path("/workspace")
AGENT_DIR = WORKSPACE_ROOT / ".agent"
TOOLS_DIR = AGENT_DIR / "tools"
CONFIG_FILE = AGENT_DIR / "config.json"


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    session_id: Optional[int] = None
    mode: str = "ask"  # ask, plan, agent
    temperature: float = 0.7
    max_tokens: Optional[int] = None  # None = unlimited (model default)
    context_files: List[Dict[str, str]] = Field(default_factory=list)


class ToolInfo(BaseModel):
    """Tool information model"""
    name: str
    description: str
    params: List[Dict[str, Any]] = Field(default_factory=list)
    source: str = "custom"


def ensure_agent_directories():
    """Ensure the agent directory structure exists"""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create default config if not exists
    if not CONFIG_FILE.exists():
        default_config = {
            "model": os.getenv("COPILOT_MODEL", "gpt-4"),
            "temperature": 0.7,
            "max_iterations": 10,
            "allowed_commands": [
                "npm", "yarn", "pnpm", "python", "pip", "git", "cat", "ls",
                "grep", "find", "echo", "mkdir", "touch", "rm", "mv", "cp"
            ]
        }
        CONFIG_FILE.write_text(json.dumps(default_config, indent=2))
    
    # Create example custom tool
    example_tool = TOOLS_DIR / "example_tool.py"
    if not example_tool.exists():
        example_tool.write_text('''"""
Example custom tool for Copilot Mode.

To create a custom tool:
1. Create a Python file in /workspace/.agent/tools/
2. Define a function decorated with @tool
3. The agent will automatically discover and use it

Example usage in chat: "Use my_custom_tool to do something"
"""
from langchain_core.tools import tool


@tool
def my_custom_tool(input_text: str) -> str:
    """
    An example custom tool that processes input text.
    
    Args:
        input_text: Text to process
        
    Returns:
        Processed result
    """
    # Replace this with your custom logic
    return f"Processed: {input_text.upper()}"
''')


def load_config() -> Dict[str, Any]:
    """Load agent configuration"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def discover_custom_tools() -> List[Any]:
    """Discover and load custom tools from the tools directory"""
    tools = []
    
    if not TOOLS_DIR.exists():
        return tools
    
    for tool_file in TOOLS_DIR.glob("*.py"):
        if tool_file.name.startswith("_"):
            continue
            
        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(
                f"custom_tool_{tool_file.stem}", tool_file
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find tool-decorated functions
                for name, obj in vars(module).items():
                    if hasattr(obj, 'name') and hasattr(obj, 'description'):
                        # This is a langchain tool
                        tools.append(obj)
                        print(f"[Agent] Loaded custom tool: {obj.name}")
        except Exception as e:
            print(f"[Agent] Warning: Failed to load tool {tool_file}: {e}")
    
    return tools


# Built-in workspace tools
def get_builtin_tools() -> List[Any]:
    """Get built-in workspace tools for native file access"""
    from langchain_core.tools import tool
    
    @tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read contents of a file in the workspace.
        
        Args:
            path: Path to the file (relative to /workspace or absolute)
            start_line: Optional start line number (1-based)
            end_line: Optional end line number (1-based)
        """
        try:
            # Resolve path
            if not path.startswith('/'):
                path = str(WORKSPACE_ROOT / path)
            
            # Security check
            resolved = Path(path).resolve()
            if not str(resolved).startswith(str(WORKSPACE_ROOT)):
                return f"Error: Path {path} is outside workspace"
            
            with open(resolved, 'r') as f:
                lines = f.readlines()
            
            if start_line and end_line:
                lines = lines[start_line-1:end_line]
            elif start_line:
                lines = lines[start_line-1:]
            
            content = ''.join(lines)
            if len(content) > 10240:
                return content[:10240] + "\n... [output truncated]"
            return content
        except Exception as e:
            return f"Error: {e}"
    
    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the workspace.
        
        Args:
            path: Path to the file (relative to /workspace or absolute)
            content: Content to write to the file
        """
        try:
            if not path.startswith('/'):
                path = str(WORKSPACE_ROOT / path)
            
            resolved = Path(path).resolve()
            if not str(resolved).startswith(str(WORKSPACE_ROOT)):
                return f"Error: Path {path} is outside workspace"
            
            # Ensure parent directory exists
            resolved.parent.mkdir(parents=True, exist_ok=True)
            
            with open(resolved, 'w') as f:
                f.write(content)
            
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error: {e}"
    
    @tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files and directories in the workspace.
        
        Args:
            path: Directory path (relative to /workspace)
            pattern: Optional glob pattern to filter results
        """
        try:
            if not path.startswith('/'):
                dir_path = WORKSPACE_ROOT / path
            else:
                dir_path = Path(path)
            
            resolved = dir_path.resolve()
            if not str(resolved).startswith(str(WORKSPACE_ROOT)):
                return f"Error: Path {path} is outside workspace"
            
            if pattern:
                files = list(resolved.glob(pattern))
            else:
                files = list(resolved.iterdir())
            
            result = []
            for f in sorted(files):
                prefix = "📁" if f.is_dir() else "📄"
                result.append(f"{prefix} {f.name}")
            
            return "\n".join(result) if result else "Empty directory"
        except Exception as e:
            return f"Error: {e}"
    
    @tool
    def search_code(query: str, path: str = ".", context_lines: int = 2) -> str:
        """Search for text in files within the workspace.
        
        Args:
            query: Text to search for
            path: Directory to search in (relative to /workspace)
            context_lines: Number of context lines around matches
        """
        import subprocess
        try:
            if not path.startswith('/'):
                search_path = str(WORKSPACE_ROOT / path)
            else:
                search_path = path
            
            # Use grep for searching
            result = subprocess.run(
                ['grep', '-rn', f'-C{context_lines}', query, search_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stdout or result.stderr or "No matches found"
            if len(output) > 10240:
                return output[:10240] + "\n... [output truncated]"
            return output
        except Exception as e:
            return f"Error: {e}"
    
    @tool
    def run_command(command: str) -> str:
        """Execute a shell command in the workspace.
        
        Args:
            command: Shell command to execute
        """
        import subprocess
        import shlex
        
        config = load_config()
        allowed_commands = config.get('allowed_commands', [])
        
        # Validate command
        try:
            parts = shlex.split(command)
            cmd_name = parts[0]
            if cmd_name not in allowed_commands:
                return f"Error: Command '{cmd_name}' is not allowed. Allowed: {', '.join(allowed_commands)}"
        except Exception as e:
            return f"Error parsing command: {e}"
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(WORKSPACE_ROOT),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout + result.stderr
            if len(output) > 10240:
                return output[:10240] + "\n... [output truncated]"
            return output or "Command completed with no output"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds"
        except Exception as e:
            return f"Error: {e}"
    
    return [read_file, write_file, list_directory, search_code, run_command]


async def create_agent():
    """Create the LangGraph agent with all tools"""
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    
    config = load_config()
    
    # Get API key from environment (injected per-request by backend proxy)
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL") or config.get("model", "gpt-4")
    
    if not api_key:
        raise ValueError("No API key configured. Set OPENAI_API_KEY or LLM_API_KEY.")
    
    # Initialize LLM
    llm_kwargs = {
        "model": model,
        "api_key": api_key,
        "temperature": config.get("temperature", 0.7),
        "streaming": True,
    }
    if base_url:
        llm_kwargs["base_url"] = base_url
    
    llm = ChatOpenAI(**llm_kwargs)
    
    # Collect all tools
    tools = get_builtin_tools()
    tools.extend(discover_custom_tools())
    
    # Create agent
    agent = create_react_agent(llm, tools)
    
    return agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    ensure_agent_directories()
    print(f"[Agent] Copilot Mode Agent starting in {WORKSPACE_ROOT}")
    yield
    print("[Agent] Shutting down...")


app = FastAPI(
    title="Copilot Mode Agent",
    description="Native AI agent running inside workspace container",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "workspace": str(WORKSPACE_ROOT),
        "tools_dir": str(TOOLS_DIR),
        "custom_tools": len(discover_custom_tools())
    }


@app.get("/tools")
async def list_tools():
    """List all available tools"""
    builtin = get_builtin_tools()
    custom = discover_custom_tools()
    
    tools = []
    for tool in builtin + custom:
        tool_info = {
            "name": tool.name,
            "description": tool.description or "",
            "source": "builtin" if tool in builtin else "custom"
        }
        
        # Extract params if available
        if hasattr(tool, 'args_schema') and tool.args_schema:
            try:
                schema = tool.args_schema
                if hasattr(schema, 'model_fields'):
                    params = []
                    for field_name, field_info in schema.model_fields.items():
                        params.append({
                            'name': field_name,
                            'type': str(field_info.annotation.__name__) if hasattr(field_info.annotation, '__name__') else 'str',
                            'description': field_info.description or '',
                        })
                    tool_info['params'] = params
            except Exception:
                pass
        
        tools.append(tool_info)
    
    return {"tools": tools}


@app.post("/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint"""
    try:
        agent = await create_agent()
        
        # Build messages
        messages = [{"role": "user", "content": request.message}]
        
        # Add context files if provided
        if request.context_files:
            context = "## Context Files:\n\n"
            for f in request.context_files:
                context += f"### {f.get('path', 'file')}\n```\n{f.get('content', '')}\n```\n\n"
            messages.insert(0, {"role": "system", "content": context})
        
        # Run agent
        result = await agent.ainvoke({"messages": messages})
        
        # Extract response
        if result.get("messages"):
            last_message = result["messages"][-1]
            content = last_message.content if hasattr(last_message, 'content') else str(last_message)
        else:
            content = str(result)
        
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint using SSE"""
    
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            agent = await create_agent()
            
            # Build messages
            messages = [{"role": "user", "content": request.message}]
            
            # Add context files
            if request.context_files:
                context = "## Context Files:\n\n"
                for f in request.context_files:
                    context += f"### {f.get('path', 'file')}\n```\n{f.get('content', '')}\n```\n\n"
                messages.insert(0, {"role": "system", "content": context})
            
            full_content = ""
            
            # Stream from agent
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2"
            ):
                kind = event.get("event")
                
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_content += chunk.content
                        yield f"data: {json.dumps({'type': 'text_chunk', 'content': chunk.content})}\n\n"
                
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': tool_name})}\n\n"
                
                elif kind == "on_tool_end":
                    output = event.get("data", {}).get("output", "")
                    yield f"data: {json.dumps({'type': 'tool_end', 'output': str(output)[:500]})}\n\n"
            
            # Signal completion
            yield f"data: {json.dumps({'type': 'complete', 'content': full_content})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
