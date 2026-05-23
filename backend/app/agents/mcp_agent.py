"""MCP-aware LangChain agent.

The agent:
1. Builds one LangChain StructuredTool per registered MCP tool at call time.
2. Sends the user message + tool list to an LLM with tool-calling enabled.
3. Executes the selected tool via the MCP executor layer.
4. Returns the final answer together with tool-selection metadata.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import StructuredTool
except ImportError:  # pragma: no cover
    from langchain.schema.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain.tools import StructuredTool

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.mcp.server import TOOL_REGISTRY, McpToolDefinition
from app.mcp.tools import execute_tool
from app.models.user import User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intelligent MCP (Model Context Protocol) assistant.
You have access to a set of specialised tools. Your job is to:
1. Understand the user's request.
2. Select the most appropriate tool from the list.
3. Provide the correct input parameters for that tool.
4. Use the tool result to compose a clear final answer.

Rules:
- Always use a tool rather than answering from memory when a tool is relevant.
- For database questions use sql_query_tool.
- For PDF questions or uploaded PDFs use pdf_rag_tool.
- For spreadsheet/CSV/XLSX/Google Sheet analysis use dataframe_analysis_tool.
- For uploaded images use image_vision_tool.
- For uploaded videos use video_analysis_tool.
- For research / academic topics use research_tool.
- For image creation use image_generation_tool.
- For everything else use general_chat.
- Include thread_id if available from context; otherwise omit it and let the server resolve one.
"""


@dataclass
class McpAgentResult:
    answer: str
    tool_used: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: dict[str, Any] | None = None
    reasoning: str = ""


def _json_schema_to_pydantic(tool_def: McpToolDefinition) -> type[BaseModel]:
    """Dynamically build a thin Pydantic model from a JSON-Schema dict for tool input validation."""
    props = tool_def.input_schema.get("properties", {})
    required = set(tool_def.input_schema.get("required", []))

    annotations: dict[str, Any] = {}
    field_defaults: dict[str, Any] = {}

    for prop_name, prop_schema in props.items():
        prop_type = prop_schema.get("type", "string")
        nullable = prop_schema.get("nullable", False)

        if prop_type == "integer":
            py_type: Any = int | None if nullable else int
        elif prop_type == "boolean":
            py_type = bool | None if nullable else bool
        else:
            py_type = str | None if nullable else str

        if prop_name not in required:
            py_type = py_type | None  # type: ignore[assignment]
            field_defaults[prop_name] = Field(default=None, description=prop_schema.get("description", ""))
        else:
            field_defaults[prop_name] = Field(description=prop_schema.get("description", ""))

        annotations[prop_name] = py_type

    model = type(
        f"{tool_def.name}_input",
        (BaseModel,),
        {"__annotations__": annotations, **field_defaults},
    )
    return model


class McpAgent:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.LITELLM_API_KEY,
            base_url=f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1",
        )

    # ------------------------------------------------------------------
    # Build LangChain StructuredTools from MCP registry (no-op executors,
    # we use the registry only for schema/description discovery by the LLM).
    # ------------------------------------------------------------------
    def _build_lc_tools(self) -> list[StructuredTool]:
        tools: list[StructuredTool] = []
        for tool_def in TOOL_REGISTRY:
            input_model = _json_schema_to_pydantic(tool_def)

            def _noop(**kwargs: Any) -> str:  # noqa: ANN401
                return json.dumps(kwargs)

            lc_tool = StructuredTool(
                name=tool_def.name,
                description=tool_def.description,
                args_schema=input_model,
                func=_noop,
                coroutine=None,
            )
            tools.append(lc_tool)
        return tools

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def run(
        self,
        message: str,
        db: AsyncSession,
        user: User,
        thread_id: int | None = None,
        file_context: str | None = None,
    ) -> McpAgentResult:
        lc_tools = self._build_lc_tools()
        llm_with_tools = self._llm.bind_tools(lc_tools)

        system_msg = SystemMessage(content=SYSTEM_PROMPT)
        thread_hint = f" (thread_id={thread_id})" if thread_id else ""
        context_block = f"\n\nUploaded file context:\n{file_context}" if file_context else ""
        human_msg = HumanMessage(content=f"{message}{thread_hint}{context_block}")

        # ── Step 1: Ask LLM to pick a tool ──────────────────────────────
        ai_response: AIMessage = await asyncio.to_thread(
            llm_with_tools.invoke, [system_msg, human_msg]
        )

        tool_calls = getattr(ai_response, "tool_calls", []) or []

        if not tool_calls:
            # LLM decided to answer directly without a tool.
            return McpAgentResult(
                answer=str(ai_response.content),
                reasoning="LLM answered directly without invoking a tool.",
            )

        # Take the first tool call (single-step agent for simplicity).
        tool_call = tool_calls[0]
        tool_name: str = tool_call.get("name", "")
        tool_args: dict[str, Any] = tool_call.get("args", {})
        tool_call_id: str = tool_call.get("id", "call_0")

        # Inject thread_id if the caller supplied one and it's missing from args.
        if thread_id and "thread_id" not in tool_args:
            tool_args["thread_id"] = thread_id

        logger.info("MCP agent selected tool=%s args=%s user=%s", tool_name, tool_args, user.id)

        # ── Step 2: Execute via MCP executor layer ───────────────────────
        try:
            tool_result = await execute_tool(
                tool_name=tool_name,
                input_data=tool_args,
                db=db,
                user=user,
            )
        except Exception as exc:
            tool_result = {"error": str(exc)}

        # ── Step 3: Let LLM compose a final natural-language answer ─────
        tool_msg = ToolMessage(
            content=json.dumps(tool_result, default=str),
            tool_call_id=tool_call_id,
        )
        final_response: AIMessage = await asyncio.to_thread(
            llm_with_tools.invoke,
            [system_msg, human_msg, ai_response, tool_msg],
        )

        return McpAgentResult(
            answer=str(final_response.content),
            tool_used=tool_name,
            tool_input=tool_args,
            tool_output=tool_result,
            reasoning=f"Selected tool '{tool_name}' based on the user request.",
        )


mcp_agent = McpAgent()
