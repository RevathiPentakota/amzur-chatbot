"""Chat API router."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.attachment import AttachmentResponse
from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse, ThreadHistoryResponse
from app.schemas.image_generation import ImageGenerateResponse
from app.services.attachment_service import attachment_service
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
        reply = await chat_service.chat(
            db,
            current_user,
            request.message,
            request.thread_id,
            request.attachment_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=reply, thread_id=request.thread_id)


@router.post("/upload", response_model=AttachmentResponse)
async def upload_attachment(
    thread_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentResponse:
    attachment = await attachment_service.upload(db, current_user, thread_id, file)
    return AttachmentResponse.model_validate(attachment)


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    attachment = await attachment_service.get_user_attachment(db, current_user, attachment_id)
    return FileResponse(
        attachment.file_path,
        media_type=attachment.mime_type,
        filename=attachment.original_filename,
    )


@router.get("/history", response_model=list[ChatHistoryItem])
async def chat_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatHistoryItem]:
    history = await chat_service.history(db, current_user)
    return [ChatHistoryItem.model_validate(item) for item in history]


@router.get("/thread/{thread_id}/messages", response_model=ThreadHistoryResponse)
async def thread_messages(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadHistoryResponse:
    try:
        messages, images = await chat_service.history_by_thread(db, current_user, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    image_items = [
        ImageGenerateResponse(
            id=img.id,
            image_url=f"/images/{img.id}/content",
            prompt=img.prompt,
            thread_id=img.thread_id,
            created_at=img.created_at,
        )
        for img in images
    ]

    return ThreadHistoryResponse(
        messages=[ChatHistoryItem.model_validate(item) for item in messages],
        images=image_items,
    )
