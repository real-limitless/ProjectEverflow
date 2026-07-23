"""Supported n8n node types for Stock Agent Emailer (v1 acceptance set).

Unknown types are still stored on import; execute will refuse them later.
"""

from __future__ import annotations

from typing import Literal

# Coarse UI category for canvas styling
NodeCategory = Literal[
    "trigger",
    "input",
    "transform",
    "logic",
    "ai",
    "output",
    "data",
    "unknown",
]

# Types required to fully run Stock Agent Emailer
SUPPORTED_NODE_TYPES: dict[str, NodeCategory] = {
    # Triggers
    "n8n-nodes-base.manualTrigger": "trigger",
    "n8n-nodes-base.scheduleTrigger": "trigger",
    "n8n-nodes-base.executeWorkflowTrigger": "trigger",
    # Files / network I/O
    "n8n-nodes-base.ftp": "input",
    "n8n-nodes-base.extractFromFile": "transform",
    "n8n-nodes-base.convertToFile": "transform",
    # Transform / control
    "n8n-nodes-base.filter": "logic",
    "n8n-nodes-base.set": "transform",
    "n8n-nodes-base.code": "transform",
    "n8n-nodes-base.aggregate": "transform",
    "n8n-nodes-base.splitOut": "transform",
    "n8n-nodes-base.splitInBatches": "logic",
    "n8n-nodes-base.if": "logic",
    # Data store
    "n8n-nodes-base.dataTable": "data",
    # Notify
    "n8n-nodes-base.emailSend": "output",
    # AI / LangChain / MCP
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": "ai",
    "@n8n/n8n-nodes-langchain.agent": "ai",
    "@n8n/n8n-nodes-langchain.mcpClientTool": "ai",
    "n8n-nodes-mcp.mcpClientTool": "ai",
}

# Credential types referenced by Stock Agent Emailer
SUPPORTED_CREDENTIAL_TYPES: frozenset[str] = frozenset(
    {
        "openAiApi",
        "ftp",
        "smtp",
        "httpMultipleHeadersAuth",
        "mcpClientApi",
    }
)

# Connection types we preserve on import
KNOWN_CONNECTION_TYPES: frozenset[str] = frozenset(
    {
        "main",
        "ai_languageModel",
        "ai_tool",
        "ai_memory",
        "ai_outputParser",
        "ai_embedding",
        "ai_vectorStore",
        "ai_document",
        "ai_textSplitter",
        "ai_toolExecutor",
    }
)

# Multi-output main handles (for canvas)
MULTI_MAIN_OUTPUT_TYPES: dict[str, list[str]] = {
    "n8n-nodes-base.if": ["true", "false"],
    "n8n-nodes-base.splitInBatches": ["done", "loop"],
    "n8n-nodes-base.switch": [],  # dynamic
}


def categorize(n8n_type: str) -> NodeCategory:
    return SUPPORTED_NODE_TYPES.get(n8n_type, "unknown")


def is_supported(n8n_type: str) -> bool:
    return n8n_type in SUPPORTED_NODE_TYPES
