"""MCP Client for the Research Agent.

Provides a thin async HTTP client that:
  1. Discovers available tools from the external MCP server (GET /tools)
  2. Invokes tools over HTTP (POST /execute)

The main backend never imports arxiv directly; all arXiv access goes through
this client talking to the external MCP server.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_CLIENT_TIMEOUT = httpx.Timeout(40.0, connect=5.0)


class McpResearchClient:
    """Async HTTP client wrapping the external MCP research server."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.RESEARCH_MCP_SERVER_URL).rstrip("/")

    # ── Tool discovery ────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch the full tool registry from the MCP server."""
        async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
            response = await client.get(f"{self._base_url}/tools")
            response.raise_for_status()
            return response.json()  # type: ignore[return-value]

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def execute(self, tool: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Call POST /execute on the MCP server.

        Args:
            tool:       Name of the tool (e.g. "search_papers")
            input_data: Tool input parameters dict

        Returns:
            The ``result`` dict from the MCP server response.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx responses
            RuntimeError:          on unexpected payload shape
        """
        payload = {"tool": tool, "input": input_data}
        logger.info("MCP client -> %s  tool=%r  input=%r", self._base_url, tool, input_data)

        async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
            response = await client.post(f"{self._base_url}/execute", json=payload)
            response.raise_for_status()

        data: dict[str, Any] = response.json()
        if data.get("status") != "success":
            raise RuntimeError(f"MCP server returned non-success status: {data}")

        result = data.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"MCP server result is not a dict: {result!r}")

        logger.info("MCP client <- tool=%r  result_keys=%s", tool, list(result.keys()))
        return result

    # ── Convenience wrappers matching tool names ──────────────────────────────

    async def search_papers(
        self,
        query: str,
        max_results: int = 5,
    ) -> dict[str, Any]:
        # Prefer canonical tool name used by backend MCP registry.
        try:
            return await self.execute("arxiv_search", {"query": query, "max_results": max_results})
        except Exception as exc:
            # Backward compatibility for older external MCP servers.
            logger.warning("MCP arxiv_search failed; falling back to search_papers: %s", exc)
            return await self.execute("search_papers", {"query": query, "max_results": max_results})

    async def get_paper_details(self, paper_id: str) -> dict[str, Any]:
        return await self.execute("get_paper_details", {"paper_id": paper_id})

    async def retrieve_abstracts(self, paper_ids: list[str]) -> dict[str, Any]:
        return await self.execute("retrieve_abstracts", {"paper_ids": paper_ids})


# Module-level singleton — imported by the research graph
mcp_research_client = McpResearchClient()
