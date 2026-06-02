"""MCP Tool Executors — thin wrappers that delegate to existing service singletons.

Design rules:
- Never duplicate business logic; always call the existing service.
- Each executor receives (input_data, db, user) and returns a plain dict.
- The router and the LangChain agent both call execute_tool().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.server import get_tool
from app.models.attachment import Attachment
from app.models.user import User
from app.services.thread_service import thread_service

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _require(data: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in data or data[k] is None]
    if missing:
        raise ValueError(f"Missing required input fields: {', '.join(missing)}")


async def _resolve_thread_id(data: dict[str, Any], db: AsyncSession, user: User) -> int:
    """Return a valid thread ID for the current user, creating one when needed."""
    requested_thread_id = data.get("thread_id")
    if requested_thread_id is not None:
        try:
            thread = await thread_service.get_thread(db, user, int(requested_thread_id))
            return int(thread.id)
        except Exception:
            # Fall back to auto-creating a thread when caller passes an invalid/stale ID.
            pass

    created = await thread_service.create_thread(db, user, title="MCP Session")
    return int(created.id)


# ── individual executors ──────────────────────────────────────────────────────

async def _exec_general_chat(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "message")
    from app.services.chat_service import chat_service

    answer = await chat_service.generate_reply(message=data["message"])
    return {"answer": answer}


async def _exec_sql_query(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "question")
    from app.services.sql_chat_service import sql_chat_service

    thread_id = await _resolve_thread_id(data, db, user)

    result = await sql_chat_service.ask(
        db_session=db,
        user=user,
        thread_id=thread_id,
        question=str(data["question"]),
    )
    return {
        "thread_id": thread_id,
        "sql": result.sql,
        "result": result.result,
        "answer": result.answer,
    }


async def _exec_pdf_rag(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "question")
    from app.ai.rag.service import rag_service

    thread_id = await _resolve_thread_id(data, db, user)

    answer = await rag_service.ask(
        db=db,
        user=user,
        thread_id=thread_id,
        question=str(data["question"]),
    )
    return {"thread_id": thread_id, "answer": answer}


async def _exec_dataframe_analysis(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "question")
    from app.services.dataframe_chat_service import dataframe_chat_service

    thread_id = await _resolve_thread_id(data, db, user)

    answer, intermediate_steps, preview = await dataframe_chat_service.chat(
        db=db,
        user=user,
        thread_id=thread_id,
        question=str(data["question"]),
    )
    return {
        "thread_id": thread_id,
        "answer": answer,
        "intermediate_steps": intermediate_steps,
        "table_preview": preview,
    }


async def _exec_arxiv_search(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "query")
    from app.agents.research_agent import mcp_research_client

    query = str(data["query"]).strip()
    max_results = int(data.get("max_results", 5))

    logger.info("MCP arxiv_search incoming query=%r", query)
    result = await mcp_research_client.search_papers(query=query, max_results=max_results)

    papers = result.get("papers", [])
    titles = [str(p.get("title", "")).strip() for p in papers if isinstance(p, dict)]

    logger.info("MCP arxiv_search retrieved paper count=%d", len(papers))
    logger.info("MCP arxiv_search retrieved paper titles=%s", titles)

    return result


async def _exec_research(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "topic")
    from app.services.research_agent_service import generate_research_digest

    thread_id = await _resolve_thread_id(data, db, user)

    digest_parts: list[str] = []
    async for chunk in generate_research_digest(
        topic=str(data["topic"]),
        db=db,
        user=user,
        thread_id=thread_id,
    ):
        # SSE chunks have format "event: ...\ndata: ...\n\n"; extract the data lines.
        for line in chunk.splitlines():
            if line.startswith("data:"):
                digest_parts.append(line[5:].strip())

    return {"thread_id": thread_id, "digest": "\n".join(digest_parts)}


async def _exec_image_generation(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    _require(data, "prompt")
    from app.services.image_generation_service import ImageGenerationService

    svc = ImageGenerationService()
    thread_id: int | None = int(data["thread_id"]) if data.get("thread_id") else None
    record = await svc.generate(db=db, user=user, prompt=str(data["prompt"]), thread_id=thread_id)
    return {
        "image_id": record.id,
        "image_url": f"/images/{record.id}/content",
        "prompt": record.prompt,
    }


async def _exec_attachment_analysis(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
    expected_file_type: str,
) -> dict[str, Any]:
    thread_id = await _resolve_thread_id(data, db, user)
    question = str(data.get("question") or "Please analyze the uploaded file.").strip()

    result = await db.scalars(
        select(Attachment)
        .where(
            Attachment.user_id == user.id,
            Attachment.thread_id == thread_id,
            Attachment.file_type == expected_file_type,
        )
        .order_by(Attachment.created_at.desc())
        .limit(4)
    )
    attachments = list(result)
    if not attachments:
        raise ValueError(f"No {expected_file_type} attachments found in this thread.")

    from app.services.chat_service import chat_service

    answer = await chat_service.generate_reply(
        message=question,
        attachments=list(reversed(attachments)),
    )
    return {
        "thread_id": thread_id,
        "analyzed_files": [item.original_filename for item in attachments],
        "answer": answer,
    }


async def _exec_image_vision(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    return await _exec_attachment_analysis(data, db, user, "image")


async def _exec_video_analysis(
    data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    return await _exec_attachment_analysis(data, db, user, "video")


# ── dispatch table ────────────────────────────────────────────────────────────

_EXECUTORS = {
    "general_chat": _exec_general_chat,
    "sql_query_tool": _exec_sql_query,
    "pdf_rag_tool": _exec_pdf_rag,
    "dataframe_analysis_tool": _exec_dataframe_analysis,
    "arxiv_search": _exec_arxiv_search,
    "research_tool": _exec_research,
    "image_generation_tool": _exec_image_generation,
    "image_vision_tool": _exec_image_vision,
    "video_analysis_tool": _exec_video_analysis,
}


async def execute_tool(
    tool_name: str,
    input_data: dict[str, Any],
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Entry point called by the router and the LangChain MCP agent."""
    definition = get_tool(tool_name)
    if definition is None:
        raise ValueError(f"Unknown MCP tool: '{tool_name}'")

    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        raise NotImplementedError(f"No executor registered for tool '{tool_name}'.")

    logger.info("MCP executing tool=%s user=%s", tool_name, user.id)
    try:
        return await executor(input_data, db, user)
    except (ValueError, LookupError):
        raise
    except Exception as exc:
        logger.exception("MCP tool execution error: tool=%s", tool_name)
        raise RuntimeError(f"Tool '{tool_name}' failed: {exc}") from exc
