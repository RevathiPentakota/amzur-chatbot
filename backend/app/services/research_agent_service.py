"""Research Digest Agent service using LangGraph with SSE streaming."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.research import ResearchState, research_graph
from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict[str, Any] | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


def _initial_state(topic: str) -> ResearchState:
    return {
        "query": topic,
        "search_round": 0,
        "max_rounds": 3,
        "papers": [],
        "summaries": [],
        "evidence_score": 0.0,
        "confidence": 0.0,
        "enough_evidence": False,
        "decision": "search_again",
        "decision_reason": "",
        "digest_sections": {},
        "final_digest": "",
        "error": "",
        "mcp_tools": [],
    }



async def _persist_research_chat(
    db: AsyncSession,
    user: User,
    thread_id: int,
    topic: str,
    final_digest: str,
) -> None:
    try:
        thread = await db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
        if not thread:
            return
        db.add(
            ChatMessage(
                user_id=user.id,
                thread_id=thread_id,
                message=f"[Research] {topic}",
                response=final_digest,
                created_at=datetime.utcnow(),
            )
        )
        await db.commit()
        if not thread.title:
            thread.title = f"Research: {topic[:60]}"
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist research chat: %s", exc)


async def generate_research_digest(
    topic: str,
    db: AsyncSession,
    user: User,
    thread_id: int,
) -> AsyncGenerator[str, None]:
    """Run LangGraph research workflow and stream SSE updates to the frontend."""
    state: dict[str, Any] = _initial_state(topic)

    yield _sse("status", {"message": "Starting LangGraph research workflow..."})

    try:
        async for chunk in research_graph.astream(state, stream_mode="updates"):
            for node_name, update in chunk.items():
                state.update(update)

                if node_name == "search_arxiv":
                    papers = state.get("papers", [])
                    round_no = state.get("search_round", 0)
                    yield _sse("status", {"message": f"Round {round_no}: searched arXiv, total papers {len(papers)}."})
                    if papers:
                        yield _sse("papers", {"papers": papers})

                elif node_name == "discover_mcp_tools":
                    tools = state.get("mcp_tools", [])
                    tool_names = [t.get("name") for t in tools]
                    yield _sse("status", {"message": f"Discovered {len(tools)} MCP tools: {tool_names}"})

                elif node_name == "summarize_papers":
                    yield _sse("status", {"message": f"Round {state.get('search_round', 0)}: summarized papers."})

                elif node_name == "evaluate_evidence":
                    yield _sse(
                        "status",
                        {
                            "message": (
                                f"Evidence score {state.get('evidence_score', 0):.2f}, "
                                f"confidence {state.get('confidence', 0):.2f}."
                            )
                        },
                    )

                elif node_name == "decide_next_step":
                    yield _sse("status", {"message": str(state.get("decision_reason", "Deciding next step."))})

                elif node_name == "generate_digest":
                    sections: dict[str, str] = state.get("digest_sections", {})
                    emit_order: list[tuple[str, str]] = [
                        ("research_topic", "Research Topic"),
                        ("key_findings", "Key Findings"),
                        ("important_papers", "Important Papers"),
                        ("trends", "Trends"),
                        ("contradictions", "Contradictions / Limitations"),
                        ("final_summary", "Final Summary"),
                    ]
                    for event_name, title in emit_order:
                        content = sections.get(event_name, "")
                        if content:
                            yield _sse(event_name, {"title": title, "content": content})

                    sources_content = sections.get("sources", "")
                    if sources_content:
                        yield _sse("sources", {"title": "Sources", "content": sources_content})

    except Exception as exc:
        logger.exception("LangGraph research workflow failed")
        yield _sse("error", {"message": f"Research workflow failed: {exc}"})
        return

    final_digest = str(state.get("final_digest", "")).strip()
    if not final_digest:
        yield _sse("error", {"message": "Unable to produce a final digest for this query."})
        return

    await _persist_research_chat(db, user, thread_id, topic, final_digest)
    yield _sse("done", {"message": "Research digest complete."})
