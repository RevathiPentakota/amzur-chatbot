from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.service import rag_service
from app.db.session import get_db
from app.models.user import User
from app.schemas.rag import RagChatRequest, RagChatResponse, RagPdfItem, RagUploadResponse
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/upload-pdf", response_model=RagUploadResponse)
async def upload_pdf(
    thread_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RagUploadResponse:
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()
        record = await rag_service.upload_pdf(
            db,
            current_user,
            thread_id,
            file.filename or "document.pdf",
            content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RagUploadResponse.model_validate(record)


@router.post("/chat", response_model=RagChatResponse)
async def rag_chat(
    request: RagChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RagChatResponse:
    try:
        answer = await rag_service.ask(db, current_user, request.thread_id, request.question)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RagChatResponse(answer=answer, thread_id=request.thread_id)


@router.get("/thread/{thread_id}/pdfs", response_model=list[RagPdfItem])
async def list_thread_pdfs(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RagPdfItem]:
    try:
        items = await rag_service.list_thread_pdfs(db, current_user, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [RagPdfItem.model_validate(item) for item in items]


@router.get("/pdfs/{pdf_id}/content")
async def get_pdf_content(
    pdf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    try:
        record = await rag_service.get_pdf(db, current_user, pdf_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(record.file_path, media_type="application/pdf", filename=record.filename)
