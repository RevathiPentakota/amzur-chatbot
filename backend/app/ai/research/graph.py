"""LangGraph workflow for autonomous arXiv research digests.

arXiv access is intentionally decoupled: all paper retrieval goes through the
external MCP server via McpResearchClient. This module never imports arxiv directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from app.agents.research_agent import mcp_research_client
from app.core.config import settings

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_SECONDS = 30
MAX_ROUNDS = 3
MAX_PAPERS_TOTAL = 12
MAX_RESULTS_PER_ROUND = 5
LOW_RELEVANCE_THRESHOLD = 0.08


class ResearchPaper(TypedDict):
    id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    url: str
    pdf_url: str


class ResearchState(TypedDict):
    query: str
    search_round: int
    max_rounds: int
    papers: list[ResearchPaper]
    summaries: list[str]
    evidence_score: float
    confidence: float
    enough_evidence: bool
    decision: Literal["search_again", "generate_digest"]
    decision_reason: str
    digest_sections: dict[str, str]
    final_digest: str
    error: str
    mcp_tools: list[dict[str, Any]]


def _normalize_query(raw: str) -> str:
    # Preserve capitalization while normalizing whitespace.
    return re.sub(r"\s+", " ", (raw or "").strip())


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-zA-Z0-9]+", text.lower()) if len(t) > 2}


def _title_similarity(query: str, title: str) -> float:
    return SequenceMatcher(None, query.lower(), title.lower()).ratio()


def _extract_topic_keywords(query: str, limit: int = 4) -> str:
    stop_words = {
        "the", "a", "an", "is", "are", "all", "of", "for", "to", "in", "on", "and", "with",
        "paper", "study", "research", "about", "please",
    }
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", query.lower()) if p]
    keywords: list[str] = []
    for token in parts:
        if len(token) <= 2 or token in stop_words:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break
    return " ".join(keywords)


def _compute_relevance(query: str, paper: ResearchPaper) -> tuple[float, bool, str]:
    """Returns (score, strong_title_match, reason)."""
    title = paper["title"]
    abstract = paper["abstract"]

    title_sim = _title_similarity(query, title)
    q_tokens = _tokenize(query)
    title_tokens = _tokenize(title)
    abstract_tokens = _tokenize(abstract)

    if not q_tokens:
        token_overlap_title = 0.0
        token_overlap_abs = 0.0
    else:
        token_overlap_title = len(q_tokens & title_tokens) / len(q_tokens)
        token_overlap_abs = len(q_tokens & abstract_tokens) / len(q_tokens)

    strong_title_match = title_sim >= 0.72 or query.lower() in title.lower()
    score = 0.60 * title_sim + 0.25 * token_overlap_title + 0.15 * token_overlap_abs

    reason = (
        f"title_sim={title_sim:.2f}, token_title={token_overlap_title:.2f}, "
        f"token_abs={token_overlap_abs:.2f}, strong_title={strong_title_match}"
    )
    return score, strong_title_match, reason


def _has_strong_abstract_keyword_match(query: str, abstract: str) -> tuple[bool, float]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return False, 0.0
    overlap = len(q_tokens & _tokenize(abstract)) / len(q_tokens)
    return overlap >= 0.30, overlap


def _json_load(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {}


async def _llm_call(prompt: str, system: str = "", max_tokens: int = 1200) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.LITELLM_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(settings.LLM_TIMEOUT_SECONDS + 10, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.LITELLM_PROXY_URL.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def _search_via_mcp(query: str, max_results: int) -> list[ResearchPaper]:
    """Retrieve papers through the external MCP server (never imports arxiv directly)."""
    try:
        data = await asyncio.wait_for(
            mcp_research_client.search_papers(query, max_results),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )

        # Be resilient to either direct result shape ({papers: [...]}) or wrapped shape ({result: {papers: [...]}}).
        payload: dict[str, Any] = data
        if isinstance(data.get("result"), dict):
            payload = data["result"]

        logger.info("Raw MCP response for query=%r: keys=%s", query, list(payload.keys()))

        raw_papers_data = payload.get("papers", [])
        raw_papers: list[dict[str, Any]] = raw_papers_data if isinstance(raw_papers_data, list) else []

        papers: list[ResearchPaper] = [
            {
                "id": str(p.get("id", "")),
                "title": str(p.get("title", "")),
                "authors": list(p.get("authors", [])),
                "abstract": str(p.get("abstract") or p.get("summary") or ""),
                "published": str(p.get("published", "Unknown")),
                "url": str(p.get("url") or p.get("pdf_url") or ""),
                "pdf_url": str(p.get("pdf_url", "")),
            }
            for p in raw_papers
        ]

        logger.info("Parsed papers count=%d for query=%r", len(papers), query)
        if papers:
            logger.info("Parsed paper titles=%s", [p["title"] for p in papers[:10]])

        return papers
    except asyncio.TimeoutError:
        logger.warning("MCP arxiv_search timeout for query: %r", query)
        return []
    except Exception as exc:
        logger.warning("MCP arxiv_search failed for query %r: %s", query, exc)
        return []


async def discover_mcp_tools(state: ResearchState) -> dict[str, Any]:
    """First graph node: discover available tools from the external MCP server."""
    try:
        tools = await asyncio.wait_for(mcp_research_client.list_tools(), timeout=10)
        logger.info("MCP tools discovered: %s", [t.get("name") for t in tools])
    except Exception as exc:
        logger.warning("MCP tool discovery failed (continuing without discovery): %s", exc)
        tools = []
    return {"mcp_tools": tools}


async def search_arxiv(state: ResearchState) -> dict[str, Any]:
    round_idx = state["search_round"] + 1
    query = _normalize_query(state["query"])

    # Use canonical topic query; the arXiv MCP tool handles exact-title strategy internally.
    exact_query = query
    found = await _search_via_mcp(exact_query, MAX_RESULTS_PER_ROUND)

    # 2) Fallback broader query if exact has no results.
    if not found:
        fallback_queries: list[str] = []

        # Explicit broader fallback requested.
        if "attention" in query.lower() or "transformer" in query.lower():
            fallback_queries.append("transformer attention")

        # Query normalization fallback.
        fallback_queries.append(query)

        # Topic extraction fallback.
        topic_keywords = _extract_topic_keywords(query)
        if topic_keywords:
            fallback_queries.append(topic_keywords)

        # Later rounds use broader intent terms.
        if round_idx >= 2:
            fallback_queries.append(f"{topic_keywords or query} survey")
        if round_idx >= 3:
            fallback_queries.append(f"{topic_keywords or query} review")

        # Preserve order and uniqueness.
        seen_fallback: set[str] = set()
        ordered_fallback: list[str] = []
        for item in fallback_queries:
            norm_item = _normalize_query(item)
            if not norm_item or norm_item in seen_fallback:
                continue
            seen_fallback.add(norm_item)
            ordered_fallback.append(norm_item)

        for fallback_query in ordered_fallback:
            fallback_found = await _search_via_mcp(fallback_query, MAX_RESULTS_PER_ROUND)
            if fallback_found:
                found = fallback_found
                break

    # De-duplicate results from multiple query variants.
    dedup_map: dict[str, ResearchPaper] = {}
    for paper in found:
        key = paper["id"] or f"{paper['title']}::{paper['published']}"
        if key not in dedup_map:
            dedup_map[key] = paper
    found = list(dedup_map.values())

    existing_ids = {paper["id"] for paper in state["papers"] if paper["id"]}
    merged = list(state["papers"])
    new_papers: list[ResearchPaper] = []
    rejection_logs: list[str] = []

    # Rank candidates by relevance but always keep strong title/abstract matches.
    scored: list[tuple[float, bool, str, ResearchPaper]] = []
    for paper in found:
        score, strong_match, detail = _compute_relevance(query, paper)
        scored.append((score, strong_match, detail, paper))
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, strong_match, detail, paper in scored:
        strong_abs_match, abs_overlap = _has_strong_abstract_keyword_match(query, paper["abstract"])

        if paper["id"] and paper["id"] in existing_ids:
            rejection_logs.append(f"Rejected duplicate: '{paper['title']}' ({detail})")
            continue

        # Always keep if strong title or strong abstract keyword match.
        keep_due_to_match = strong_match or strong_abs_match

        if score < LOW_RELEVANCE_THRESHOLD and not keep_due_to_match:
            rejection_logs.append(
                f"Rejected low relevance: '{paper['title']}' ({detail}, abs_overlap={abs_overlap:.2f})"
            )
            continue

        merged.append(paper)
        new_papers.append(paper)
        logger.info(
            "Accepted paper: '%s' (score=%.2f, strong_title=%s, strong_abs=%s, abs_overlap=%.2f)",
            paper["title"],
            score,
            strong_match,
            strong_abs_match,
            abs_overlap,
        )
        if len(merged) >= MAX_PAPERS_TOTAL:
            break

    logger.info("Filtered papers: accepted=%d rejected=%d", len(new_papers), len(rejection_logs))
    for line in rejection_logs:
        logger.info(line)

    reason = f"Round {round_idx}: found {len(new_papers)} new paper(s), total {len(merged)}."

    return {
        "search_round": round_idx,
        "papers": merged,
        "decision_reason": reason,
        "error": "",
    }


async def summarize_papers(state: ResearchState) -> dict[str, Any]:
    if not state["papers"]:
        return {
            "summaries": state["summaries"] + ["No relevant papers found yet."],
            "decision_reason": "No papers available for summarization.",
        }

    focus = state["papers"][:8]
    context = "\n\n".join(
        f"[{i+1}] {paper['title']}\n"
        f"Authors: {', '.join(paper['authors'][:4])}\n"
        f"Abstract: {paper['abstract'][:700]}"
        for i, paper in enumerate(focus)
    )

    prompt = (
        "Summarize the current evidence as concise research notes. "
        "Include: (1) 4-6 key findings, (2) strong recurring themes, "
        "(3) open questions/limitations.\n\n"
        f"Research question: {state['query']}\n\n"
        f"Papers:\n{context}"
    )

    try:
        summary = await _llm_call(prompt, system="You are a precise research analyst.")
    except Exception as exc:
        summary = f"Summary generation failed: {exc}"

    return {
        "summaries": state["summaries"] + [summary],
        "decision_reason": f"Generated summary for round {state['search_round']}.",
    }


async def evaluate_evidence(state: ResearchState) -> dict[str, Any]:
    papers_count = len(state["papers"])
    summary_count = len(state["summaries"])
    query = _normalize_query(state["query"])

    if papers_count:
        logger.info("Retrieved papers before evidence evaluation (%s):", papers_count)
        for idx, paper in enumerate(state["papers"][:12], start=1):
            logger.info("  [%s] %s", idx, paper["title"])

    latest_summary = state["summaries"][-1] if state["summaries"] else ""

    prompt = (
        "Evaluate whether the available evidence is sufficient to produce a reliable research digest. "
        "Return JSON only with keys: evidence_score (0-1), confidence (0-1), enough_evidence (bool), reason (string).\n\n"
        f"Query: {state['query']}\n"
        f"Papers count: {papers_count}\n"
        f"Search rounds: {state['search_round']} / {state['max_rounds']}\n"
        f"Latest summary:\n{latest_summary[:2500]}"
    )

    # Heuristic baseline with stronger relevance awareness.
    title_sims: list[float] = []
    abstract_rel: list[float] = []
    strong_title_hits = 0
    q_tokens = _tokenize(query)
    for paper in state["papers"]:
        t_sim = _title_similarity(query, paper["title"])
        title_sims.append(t_sim)
        if t_sim >= 0.72 or query.lower() in paper["title"].lower():
            strong_title_hits += 1
        if q_tokens:
            rel = len(q_tokens & _tokenize(paper["abstract"])) / len(q_tokens)
        else:
            rel = 0.0
        abstract_rel.append(rel)

    best_title_sim = max(title_sims) if title_sims else 0.0
    avg_title_sim = sum(title_sims) / len(title_sims) if title_sims else 0.0
    avg_abs_rel = sum(abstract_rel) / len(abstract_rel) if abstract_rel else 0.0
    strong_semantic_hits = sum(1 for rel in abstract_rel if rel >= 0.30)

    score = min(
        1.0,
        0.18
        + papers_count * 0.06
        + summary_count * 0.08
        + best_title_sim * 0.28
        + avg_abs_rel * 0.20,
    )
    confidence = min(
        1.0,
        0.16
        + papers_count * 0.05
        + strong_title_hits * 0.10
        + avg_title_sim * 0.22
        + avg_abs_rel * 0.17,
    )

    enough = (
        (score >= 0.68)
        or (strong_title_hits >= 1 and best_title_sim >= 0.78 and avg_abs_rel >= 0.15)
        or (strong_title_hits >= 1 and best_title_sim >= 0.78)
        or (strong_semantic_hits >= 1)
        or (strong_title_hits >= 2 and papers_count >= 3)
        or (state["search_round"] >= state["max_rounds"])
    )
    reason = "Heuristic evaluation."

    try:
        result = _json_load(await _llm_call(prompt, max_tokens=300))
        if isinstance(result.get("evidence_score"), (float, int)):
            score = max(0.0, min(float(result["evidence_score"]), 1.0))
        if isinstance(result.get("confidence"), (float, int)):
            confidence = max(0.0, min(float(result["confidence"]), 1.0))
        if isinstance(result.get("enough_evidence"), bool):
            enough = bool(result["enough_evidence"])
        if isinstance(result.get("reason"), str) and result["reason"].strip():
            reason = result["reason"].strip()
    except Exception:
        pass

    if state["search_round"] >= state["max_rounds"]:
        enough = True

    logger.info(
        "Evidence evaluation: score=%.3f confidence=%.3f enough=%s strong_title_hits=%d strong_semantic_hits=%d best_title_sim=%.2f avg_abs_rel=%.2f",
        score,
        confidence,
        enough,
        strong_title_hits,
        strong_semantic_hits,
        best_title_sim,
        avg_abs_rel,
    )

    return {
        "evidence_score": round(score, 3),
        "confidence": round(confidence, 3),
        "enough_evidence": enough,
        "decision_reason": reason,
    }


async def decide_next_step(state: ResearchState) -> dict[str, Any]:
    if not state["enough_evidence"] and state["search_round"] < state["max_rounds"]:
        return {
            "decision": "search_again",
            "decision_reason": (
                f"Evidence score {state['evidence_score']:.2f} is below threshold; "
                "performing another search round."
            ),
        }
    return {
        "decision": "generate_digest",
        "decision_reason": (
            f"Evidence accepted (score {state['evidence_score']:.2f}, "
            f"confidence {state['confidence']:.2f})."
        ),
    }


async def generate_digest(state: ResearchState) -> dict[str, Any]:
    papers = state["papers"][:10]

    paper_context = "\n\n".join(
        f"[{i+1}] {paper['title']} ({paper['published']})\n"
        f"Authors: {', '.join(paper['authors'][:4])}\n"
        f"Abstract: {paper['abstract'][:700]}"
        for i, paper in enumerate(papers)
    )

    summary_context = "\n\n".join(
        f"Round {i+1} Summary:\n{text[:1500]}"
        for i, text in enumerate(state["summaries"][-3:])
    )

    system = (
        "You are a senior research analyst. Use only provided paper metadata and summaries. "
        "Be concise, evidence-based, and cite paper numbers like [1], [2]."
    )

    prompts: list[tuple[str, str, str]] = [
        (
            "research_topic",
            "Research Topic",
            f"Write 2-3 lines describing the exact research topic and scope for: {state['query']}",
        ),
        (
            "key_findings",
            "Key Findings",
            "Provide 4-6 high-confidence findings with concise evidence references.",
        ),
        (
            "important_papers",
            "Important Papers",
            "List the most important papers and why each matters.",
        ),
        (
            "trends",
            "Trends",
            "Identify 2-4 major trends in methods/results.",
        ),
        (
            "contradictions",
            "Contradictions / Limitations",
            "Highlight contradictions, limitations, and unresolved questions.",
        ),
        (
            "final_summary",
            "Final Summary",
            "Write a concise final synthesis in 4-6 sentences.",
        ),
    ]

    sections: dict[str, str] = {}
    for key, title, instruction in prompts:
        prompt = (
            f"{instruction}\n\n"
            f"Research question: {state['query']}\n"
            f"Evidence score: {state['evidence_score']}\n"
            f"Confidence: {state['confidence']}\n\n"
            f"Paper list:\n{paper_context}\n\n"
            f"Previous summaries:\n{summary_context}"
        )
        try:
            sections[key] = await _llm_call(prompt, system=system)
        except Exception as exc:
            sections[key] = f"Unable to generate {title.lower()}: {exc}"

    sources_md = "\n".join(
        f"[{i+1}] [{paper['title']}]({paper['url']}) | PDF: {paper['pdf_url']}"
        for i, paper in enumerate(papers)
    )
    sections["sources"] = sources_md

    final_digest_parts = [f"# Research Digest\n\n## Research Topic\n{sections['research_topic']}"]
    final_digest_parts.extend(
        [
            f"\n## Key Findings\n{sections['key_findings']}",
            f"\n## Important Papers\n{sections['important_papers']}",
            f"\n## Trends\n{sections['trends']}",
            f"\n## Contradictions / Limitations\n{sections['contradictions']}",
            f"\n## Final Summary\n{sections['final_summary']}",
            f"\n## Sources\n{sections['sources']}",
        ]
    )

    return {
        "digest_sections": sections,
        "final_digest": "\n".join(final_digest_parts),
    }


def _route_from_decision(state: ResearchState) -> str:
    return state.get("decision", "generate_digest")


def build_research_graph() -> Any:
    graph = StateGraph(ResearchState)

    graph.add_node("discover_mcp_tools", discover_mcp_tools)
    graph.add_node("search_arxiv", search_arxiv)
    graph.add_node("summarize_papers", summarize_papers)
    graph.add_node("evaluate_evidence", evaluate_evidence)
    graph.add_node("decide_next_step", decide_next_step)
    graph.add_node("generate_digest", generate_digest)

    graph.add_edge(START, "discover_mcp_tools")
    graph.add_edge("discover_mcp_tools", "search_arxiv")
    graph.add_edge("search_arxiv", "summarize_papers")
    graph.add_edge("summarize_papers", "evaluate_evidence")
    graph.add_edge("evaluate_evidence", "decide_next_step")
    graph.add_conditional_edges(
        "decide_next_step",
        _route_from_decision,
        {
            "search_again": "search_arxiv",
            "generate_digest": "generate_digest",
        },
    )
    graph.add_edge("generate_digest", END)

    return graph.compile()


research_graph = build_research_graph()
