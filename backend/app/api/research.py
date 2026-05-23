"""Research Digest API router — streaming SSE endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.research_agent_service import generate_research_digest

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    topic: str
    thread_id: int


@router.post("/digest")
async def research_digest(
    request: ResearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream a structured research digest for the given topic.
    Returns text/event-stream with named SSE events:
      - status   : progress messages
      - papers   : list of retrieved paper metadata
      - key_findings / trends / contradictions / final_summary : digest sections
      - sources  : cited sources
      - done     : completion signal
      - error    : on failure
    """
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="Topic must not be empty.")
    if len(topic) > 500:
        raise HTTPException(status_code=422, detail="Topic too long (max 500 chars).")

    return StreamingResponse(
        generate_research_digest(topic, db, current_user, request.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
