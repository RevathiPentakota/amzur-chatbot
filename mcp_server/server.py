"""External MCP Server — exposes arXiv as a set of MCP tools.

Runs as a standalone FastAPI process (separate from the main backend).

Start with:
    uvicorn mcp_server.server:app --host 0.0.0.0 --port 8001 --reload

Endpoints:
    GET  /tools          List all available tools with full schemas
    POST /execute        Invoke a named tool with structured input
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mcp_server.tools import arxiv_tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Research MCP Server",
    description="External MCP server exposing arXiv academic search tools.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    tool: str
    input: dict[str, Any]


class ExecuteResponse(BaseModel):
    status: str
    result: dict[str, Any]


# ── Tool registry (all providers merged here) ─────────────────────────────────

ALL_TOOLS: list[dict[str, Any]] = arxiv_tool.TOOL_DEFINITIONS


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/tools", response_model=list[dict[str, Any]])
async def list_tools() -> list[dict[str, Any]]:
    """Return metadata for all registered MCP tools."""
    return ALL_TOOLS


@app.post("/execute", response_model=ExecuteResponse)
async def execute_tool(payload: ExecuteRequest) -> ExecuteResponse:
    """
    Invoke a named MCP tool.

    Body:
        {
            "tool": "search_papers",
            "input": { "query": "attention mechanism transformers", "max_results": 5 }
        }
    """
    tool_name = payload.tool.strip()

    # Route to the correct provider
    arxiv_tool_names = {td["name"] for td in arxiv_tool.TOOL_DEFINITIONS}

    try:
        if tool_name in arxiv_tool_names:
            result = await arxiv_tool.execute(tool_name, payload.input)
        else:
            raise LookupError(f"Unknown tool: {tool_name!r}")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Tool execution error for %r", tool_name)
        raise HTTPException(status_code=502, detail=f"Tool execution failed: {exc}") from exc

    return ExecuteResponse(status="success", result=result)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "server": "research-mcp-server"}
