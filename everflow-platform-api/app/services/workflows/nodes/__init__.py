"""Node executors registry."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes import core, data_io, files, llm_agent

# Executor returns multi-output: list of (output_index, items)
NodeResult = list[tuple[int, list[ExecutionItem]]]
Executor = Callable[..., Awaitable[NodeResult]]


async def dispatch(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: Any,
) -> NodeResult:
    """Route to the correct executor. ctx is EngineContext."""
    t = node.type
    table: dict[str, Executor] = {
        "n8n-nodes-base.manualTrigger": core.exec_trigger,
        "n8n-nodes-base.scheduleTrigger": core.exec_trigger,
        "n8n-nodes-base.executeWorkflowTrigger": core.exec_trigger,
        "n8n-nodes-base.set": core.exec_set,
        "n8n-nodes-base.filter": core.exec_filter,
        "n8n-nodes-base.if": core.exec_if,
        "n8n-nodes-base.code": core.exec_code,
        "n8n-nodes-base.aggregate": core.exec_aggregate,
        "n8n-nodes-base.splitOut": core.exec_split_out,
        "n8n-nodes-base.splitInBatches": core.exec_split_in_batches,
        "n8n-nodes-base.extractFromFile": files.exec_extract_from_file,
        "n8n-nodes-base.convertToFile": files.exec_convert_to_file,
        "n8n-nodes-base.ftp": data_io.exec_ftp,
        "n8n-nodes-base.dataTable": data_io.exec_data_table,
        "n8n-nodes-base.emailSend": data_io.exec_email_send,
        "@n8n/n8n-nodes-langchain.lmChatOpenAi": llm_agent.exec_lm_chat_openai,
        "@n8n/n8n-nodes-langchain.agent": llm_agent.exec_agent,
        "@n8n/n8n-nodes-langchain.mcpClientTool": llm_agent.exec_mcp_tool_stub,
        "n8n-nodes-mcp.mcpClientTool": llm_agent.exec_mcp_tool_stub,
    }
    fn = table.get(t)
    if fn is None:
        raise RuntimeError(f"Unsupported node type for execution: {t}")
    return await fn(node, items, ctx=ctx)
