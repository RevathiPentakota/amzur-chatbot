"""MCP Tool Registry — defines metadata/schema for every available tool.

Each entry in TOOL_REGISTRY describes:
- name       : unique tool identifier
- description: what the LLM sees when deciding which tool to use
- input_schema : JSON-Schema-style dict of accepted parameters
- output_schema: description of what the tool returns
- requires_thread_id: whether the tool needs a persisted chat thread

No business logic lives here — only metadata.
Actual execution is in app/mcp/tools.py.
"""
from __future__ import annotations

from typing import Any


class McpToolDefinition:
    __slots__ = ("name", "description", "input_schema", "output_schema", "requires_thread_id")

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        requires_thread_id: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.requires_thread_id = requires_thread_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "requires_thread_id": self.requires_thread_id,
        }


TOOL_REGISTRY: list[McpToolDefinition] = [
    McpToolDefinition(
        name="general_chat",
        description=(
            "General-purpose conversational AI. Use this for any open-ended question, "
            "explanation, summarisation, or task that does not require a specialised tool."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The user message or question."},
            },
            "required": ["message"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
            },
        },
        requires_thread_id=False,
    ),
    McpToolDefinition(
        name="sql_query_tool",
        description=(
            "Translate a natural-language question into a PostgreSQL SELECT query, execute it "
            "against the application database, and return the SQL, raw rows, and a plain-English "
            "explanation. Use when the user asks about data in the database, employee records, "
            "orders, statistics, or any structured database content."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural-language question about the database."},
                "thread_id": {"type": "integer", "description": "Thread ID for persistence."},
            },
            "required": ["question", "thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "result": {"type": "array", "items": {"type": "object"}},
                "answer": {"type": "string"},
            },
        },
        requires_thread_id=True,
    ),
    McpToolDefinition(
        name="pdf_rag_tool",
        description=(
            "Answer a question using previously uploaded PDF documents via semantic retrieval "
            "(RAG). Use when the user wants to query, summarise, or extract information from "
            "a PDF they have uploaded."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question to answer from the PDF."},
                "thread_id": {"type": "integer", "description": "Thread ID that has PDFs indexed."},
            },
            "required": ["question", "thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
            },
        },
        requires_thread_id=True,
    ),
    McpToolDefinition(
        name="dataframe_analysis_tool",
        description=(
            "Analyse a CSV, Excel, or Google Sheet that the user previously uploaded or connected "
            "in a thread. Answers questions, computes statistics, filters rows, and creates "
            "summaries using a Pandas agent. Use when the user asks about data in a spreadsheet."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Analytical question about the dataset."},
                "thread_id": {"type": "integer", "description": "Thread ID with an uploaded data source."},
            },
            "required": ["question", "thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "intermediate_steps": {"type": "string"},
                "table_preview": {"type": "array", "items": {"type": "object"}},
            },
        },
        requires_thread_id=True,
    ),
    McpToolDefinition(
        name="arxiv_search",
        description=(
            "Search arXiv for academic papers matching a query string. "
            "Returns paper metadata including title, authors, abstract, and links."
        ),
        input_schema={
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
        output_schema={
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
        requires_thread_id=False,
    ),
    McpToolDefinition(
        name="research_tool",
        description=(
            "Search arXiv for academic papers on a topic, summarise findings, identify trends "
            "and contradictions, and produce a structured research digest. Use when the user "
            "asks for a literature review, research summary, or paper recommendations."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Research topic or question."},
                "thread_id": {"type": "integer", "description": "Thread ID for persistence."},
            },
            "required": ["topic", "thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "digest": {"type": "string", "description": "Full research digest text."},
            },
        },
        requires_thread_id=True,
    ),
    McpToolDefinition(
        name="image_generation_tool",
        description=(
            "Generate an image from a text description using an AI image model. "
            "Returns a URL to the generated image. Use when the user asks to create, "
            "draw, illustrate, or generate any image."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed image description."},
                "thread_id": {"type": "integer", "description": "Optional thread ID.", "nullable": True},
            },
            "required": ["prompt"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "image_id": {"type": "integer"},
                "image_url": {"type": "string"},
                "prompt": {"type": "string"},
            },
        },
        requires_thread_id=False,
    ),
    McpToolDefinition(
        name="image_vision_tool",
        description=(
            "Analyze image attachments uploaded in the current thread. Use when the user asks "
            "to describe, summarize, extract text, or reason about uploaded images."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question about uploaded image attachments.",
                    "nullable": True,
                },
                "thread_id": {"type": "integer", "description": "Thread ID with uploaded images."},
            },
            "required": ["thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "integer"},
                "analyzed_files": {"type": "array", "items": {"type": "string"}},
                "answer": {"type": "string"},
            },
        },
        requires_thread_id=True,
    ),
    McpToolDefinition(
        name="video_analysis_tool",
        description=(
            "Analyze video attachments uploaded in the current thread by using extracted frames. "
            "Use when the user asks to summarize or understand uploaded videos."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question about uploaded video attachments.",
                    "nullable": True,
                },
                "thread_id": {"type": "integer", "description": "Thread ID with uploaded videos."},
            },
            "required": ["thread_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "integer"},
                "analyzed_files": {"type": "array", "items": {"type": "string"}},
                "answer": {"type": "string"},
            },
        },
        requires_thread_id=True,
    ),
]

TOOL_MAP: dict[str, McpToolDefinition] = {t.name: t for t in TOOL_REGISTRY}


def get_tool(name: str) -> McpToolDefinition | None:
    return TOOL_MAP.get(name)


def list_tools() -> list[dict]:
    return [t.to_dict() for t in TOOL_REGISTRY]
