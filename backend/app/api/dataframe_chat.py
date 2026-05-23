from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.dataframe_chat import (
    DataFrameChatRequest,
    DataFrameChatResponse,
    DataFrameSourceResponse,
    GoogleSheetConnectRequest,
)
from app.services.auth_service import get_current_user
from app.services.dataframe_chat_service import dataframe_chat_service

router = APIRouter(prefix="/dataframe", tags=["dataframe"])


def _source_mime_type(source_type: str) -> str:
    if source_type == "csv":
        return "text/csv"
    if source_type == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if source_type == "google_sheet":
        return "application/vnd.google-apps.spreadsheet"
    return "application/octet-stream"


@router.post("/upload", response_model=DataFrameSourceResponse)
async def upload_dataframe(
    thread_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataFrameSourceResponse:
    try:
        source, preview = await dataframe_chat_service.upload_file(db, current_user, thread_id, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DataFrameSourceResponse(
        id=source.id,
        file_id=source.id,
        user_id=source.user_id,
        thread_id=source.thread_id,
        filename=source.filename,
        file_type="spreadsheet",
        mime_type=_source_mime_type(source.source_type),
        file_url="",
        file_path=source.file_path,
        source_type=source.source_type,
        google_sheet_id=source.google_sheet_id,
        worksheet_name=source.worksheet_name,
        created_at=source.created_at,
        table_preview=preview,
    )


@router.post("/google-sheet", response_model=DataFrameSourceResponse)
async def connect_google_sheet(
    request: GoogleSheetConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataFrameSourceResponse:
    try:
        source, preview = await dataframe_chat_service.connect_google_sheet(
            db,
            current_user,
            request.thread_id,
            request.sheet,
            request.worksheet_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DataFrameSourceResponse(
        id=source.id,
        file_id=source.id,
        user_id=source.user_id,
        thread_id=source.thread_id,
        filename=source.filename,
        file_type="spreadsheet",
        mime_type=_source_mime_type(source.source_type),
        file_url="",
        file_path=source.file_path,
        source_type=source.source_type,
        google_sheet_id=source.google_sheet_id,
        worksheet_name=source.worksheet_name,
        created_at=source.created_at,
        table_preview=preview,
    )


@router.post("/chat", response_model=DataFrameChatResponse)
async def dataframe_chat(
    request: DataFrameChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataFrameChatResponse:
    try:
        answer, steps, preview = await dataframe_chat_service.chat(
            db,
            current_user,
            request.thread_id,
            request.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DataFrameChatResponse(answer=answer, intermediate_steps=steps, table_preview=preview)


@router.get("/thread/{thread_id}/sources", response_model=list[DataFrameSourceResponse])
async def list_thread_sources(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DataFrameSourceResponse]:
    try:
        items = await dataframe_chat_service.list_thread_sources(db, current_user, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    responses: list[DataFrameSourceResponse] = []
    for item in items:
        response = DataFrameSourceResponse(
            id=item.id,
            file_id=item.id,
            user_id=item.user_id,
            thread_id=item.thread_id,
            filename=item.filename,
            file_type="spreadsheet",
            mime_type=_source_mime_type(item.source_type),
            file_url="",
            file_path=item.file_path,
            source_type=item.source_type,
            google_sheet_id=item.google_sheet_id,
            worksheet_name=item.worksheet_name,
            created_at=item.created_at,
            table_preview=[],
        )
        responses.append(response)
    return responses
