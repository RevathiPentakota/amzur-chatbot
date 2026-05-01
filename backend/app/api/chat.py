"""Chat API router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from app.services.auth_service import get_current_user
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    try:
        reply = await chat_service.chat(db, current_user, request.message, request.thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatResponse(reply=reply, thread_id=request.thread_id)


@router.get("/history", response_model=list[ChatHistoryItem])
async def chat_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatHistoryItem]:
    history = await chat_service.history(db, current_user)
    return [ChatHistoryItem.model_validate(item) for item in history]


@router.get("/thread/{thread_id}/messages", response_model=list[ChatHistoryItem])
async def thread_messages(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatHistoryItem]:
    try:
        history = await chat_service.history_by_thread(db, current_user, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ChatHistoryItem.model_validate(item) for item in history]
