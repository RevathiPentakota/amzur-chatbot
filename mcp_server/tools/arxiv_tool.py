"""arXiv MCP Tool — three callable actions exposed to the MCP server.

Actions:
  - search_papers      : full-text/title search returning paper metadata
  - get_paper_details  : fetch a single paper by arXiv ID
  - retrieve_abstracts : bulk-fetch abstracts for a list of IDs
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import arxiv

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT = 30
DEFAULT_MAX_RESULTS = 5


def _simplify_keywords(text: str) -> str:
    tokens = [t.strip() for t in text.lower().replace('"', " ").split() if t.strip()]
    stop_words = {
        "the", "a", "an", "is", "are", "of", "for", "to", "in", "on", "and", "with",
        "paper", "study", "research", "about", "please",
    }
    keywords = [t for t in tokens if len(t) > 2 and t not in stop_words]
    return " ".join(keywords[:6]).strip()


def _run_search(search: arxiv.Search) -> list[Any]:
    """Run search across arxiv package versions while preserving requested call style."""
    try:
        results = list(search.results())
        return results
    except AttributeError:
        # arxiv>=2.x uses Client.results(search)
        client = arxiv.Client()
        return list(client.results(search))

# ── Tool metadata (MCP-compatible schema) ────────────────────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "arxiv_search",
        "description": (
            "Search arXiv for academic papers matching a query string. "
            "Returns paper id, title, authors, abstract, published date, url, and pdf_url."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (title, keywords, author, etc.).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return (1-20). Default 5.",
                },
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "papers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "authors": {"type": "array", "items": {"type": "string"}},
                            "abstract": {"type": "string"},
                            "published": {"type": "string"},
                            "url": {"type": "string"},
                            "pdf_url": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        },
    },
    {
        "name": "search_papers",
        "description": (
            "Search arXiv for academic papers matching a query string. "
            "Returns paper id, title, authors, abstract, published date, url, and pdf_url."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (title, keywords, author, etc.).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return (1-20). Default 5.",
                },
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "papers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "authors": {"type": "array", "items": {"type": "string"}},
                            "abstract": {"type": "string"},
                            "published": {"type": "string"},
                            "url": {"type": "string"},
                            "pdf_url": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_paper_details",
        "description": (
            "Fetch full metadata for a single arXiv paper using its arXiv ID "
            "(e.g. '2307.09288' or the full URL 'https://arxiv.org/abs/2307.09288')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paper_id": {
                    "type": "string",
                    "description": "arXiv paper ID or full arXiv URL.",
                },
            },
            "required": ["paper_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "paper": {"type": "object"},
            },
        },
    },
    {
        "name": "retrieve_abstracts",
        "description": (
            "Retrieve only the abstract text for a batch of arXiv paper IDs. "
            "Useful when you already have IDs and only need the text content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paper_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of arXiv paper IDs.",
                },
            },
            "required": ["paper_ids"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "abstracts": {
                    "type": "object",
                    "description": "Mapping of paper_id -> abstract text.",
                },
            },
        },
    },
]


# ── Internal sync helpers (run inside thread executor) ──────────────────────

def _search_sync(query: str, max_results: int) -> list[dict[str, Any]]:
    # 1) Exact-title query first.
    exact_query = f'ti:"{query}"'
    fallback_query = "transformer attention"
    keyword_query = _simplify_keywords(query)

    query_attempts = [exact_query, fallback_query]
    if keyword_query and keyword_query not in query_attempts:
        query_attempts.append(keyword_query)

    results: list[Any] = []
    final_query = exact_query
    for attempt in query_attempts:
        final_query = attempt
        print("FINAL QUERY:", final_query)
        logger.info("arXiv search_papers attempt: query=%r", final_query)
        search = arxiv.Search(
            query=final_query,
            max_results=5,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = _run_search(search)
        print("RESULT COUNT:", len(results))
        for r in results:
            print("TITLE:", getattr(r, "title", ""))
        if results:
            break

    papers: list[dict[str, Any]] = []
    for item in results:
        papers.append(
            {
                "title": (item.title or "").strip(),
                "authors": [a.name for a in item.authors[:8]],
                "summary": (item.summary or "").strip(),
                "abstract": (item.summary or "").strip(),
                "published": item.published.strftime("%Y-%m-%d") if item.published else "Unknown",
                "pdf_url": item.pdf_url or (item.entry_id or "").strip(),
            }
        )
    return papers


def _get_paper_sync(paper_id: str) -> dict[str, Any] | None:
    # Strip full URL prefix if provided.
    clean_id = paper_id.replace("https://arxiv.org/abs/", "").strip()
    logger.info("arXiv get_paper_details: id=%r", clean_id)
    search = arxiv.Search(id_list=[clean_id])
    results = list(search.results())
    if not results:
        return None
    item = results[0]
    return {
        "id": (item.entry_id or "").strip(),
        "title": (item.title or "").strip(),
        "authors": [a.name for a in item.authors],
        "abstract": (item.summary or "").strip(),
        "published": item.published.strftime("%Y-%m-%d") if item.published else "Unknown",
        "url": (item.entry_id or "").strip(),
        "pdf_url": item.pdf_url or (item.entry_id or "").strip(),
        "categories": item.categories,
        "comment": item.comment or "",
    }


def _bulk_abstracts_sync(paper_ids: list[str]) -> dict[str, str]:
    clean_ids = [pid.replace("https://arxiv.org/abs/", "").strip() for pid in paper_ids]
    logger.info("arXiv retrieve_abstracts: ids=%r", clean_ids)
    search = arxiv.Search(id_list=clean_ids)
    abstracts: dict[str, str] = {}
    for item in search.results():
        abstracts[(item.entry_id or "").strip()] = (item.summary or "").strip()
    return abstracts


# ── Async public API ─────────────────────────────────────────────────────────

async def search_papers(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> dict[str, Any]:
    max_results = max(1, min(max_results, 20))
    loop = asyncio.get_event_loop()
    try:
        papers = await asyncio.wait_for(
            loop.run_in_executor(None, _search_sync, query, max_results),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("arXiv search_papers timeout for query: %r", query)
        papers = []
    except Exception as exc:
        logger.error("arXiv search_papers error: %s", exc)
        papers = []
    return {"papers": papers, "total": len(papers)}


async def get_paper_details(paper_id: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    try:
        paper = await asyncio.wait_for(
            loop.run_in_executor(None, _get_paper_sync, paper_id),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("arXiv get_paper_details timeout for id: %r", paper_id)
        paper = None
    except Exception as exc:
        logger.error("arXiv get_paper_details error: %s", exc)
        paper = None
    return {"paper": paper}


async def retrieve_abstracts(paper_ids: list[str]) -> dict[str, Any]:
    if not paper_ids:
        return {"abstracts": {}}
    loop = asyncio.get_event_loop()
    try:
        abstracts = await asyncio.wait_for(
            loop.run_in_executor(None, _bulk_abstracts_sync, paper_ids),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("arXiv retrieve_abstracts timeout")
        abstracts = {}
    except Exception as exc:
        logger.error("arXiv retrieve_abstracts error: %s", exc)
        abstracts = {}
    return {"abstracts": abstracts}


# ── Dispatcher (called by the MCP server) ────────────────────────────────────

async def execute(tool_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the correct arXiv action."""
    if tool_name in {"arxiv_search", "search_papers"}:
        query = str(input_data.get("query", "")).strip()
        if not query:
            raise ValueError("'query' is required for arxiv_search")
        max_results = int(input_data.get("max_results", DEFAULT_MAX_RESULTS))
        return await search_papers(query, max_results)

    if tool_name == "get_paper_details":
        paper_id = str(input_data.get("paper_id", "")).strip()
        if not paper_id:
            raise ValueError("'paper_id' is required for get_paper_details")
        return await get_paper_details(paper_id)

    if tool_name == "retrieve_abstracts":
        ids = input_data.get("paper_ids", [])
        if not isinstance(ids, list):
            raise ValueError("'paper_ids' must be a list of strings")
        return await retrieve_abstracts(ids)

    raise LookupError(f"Unknown arXiv tool: {tool_name!r}")
