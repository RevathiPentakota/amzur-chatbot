"""MCP API router — exposes tool discovery and execution endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.mcp_agent import McpAgentResult, mcp_agent
from app.db.session import get_db
from app.mcp.server import list_tools
from app.mcp.tools import execute_tool
from app.models.user import User
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class McpExecuteRequest(BaseModel):
    tool: str
    input: dict[str, Any]


class McpExecuteResponse(BaseModel):
    status: str
    result: dict[str, Any]


class McpAgentRequest(BaseModel):
    message: str
    thread_id: int | None = None
    file_context: str | None = None


class McpAgentResponse(BaseModel):
    answer: str
    tool_used: str | None
    tool_input: dict[str, Any] | None
    tool_output: dict[str, Any] | None
    reasoning: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tools")
async def get_tools(
    _: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all registered MCP tool definitions with input/output schemas."""
    return list_tools()


@router.post("/execute", response_model=McpExecuteResponse)
async def execute(
    payload: McpExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> McpExecuteResponse:
    """Directly invoke a named MCP tool with the supplied input."""
    try:
        result = await execute_tool(
            tool_name=payload.tool,
            input_data=payload.input,
            db=db,
            user=current_user,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return McpExecuteResponse(status="success", result=result)


@router.post("/agent", response_model=McpAgentResponse)
async def run_agent(
    payload: McpAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> McpAgentResponse:
    """Run the LangChain MCP agent: it selects the right tool and returns a composed answer."""
    try:
        result: McpAgentResult = await mcp_agent.run(
            message=payload.message,
            db=db,
            user=current_user,
            thread_id=payload.thread_id,
            file_context=payload.file_context,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return McpAgentResponse(
        answer=result.answer,
        tool_used=result.tool_used,
        tool_input=result.tool_input,
        tool_output=result.tool_output,
        reasoning=result.reasoning,
    )
