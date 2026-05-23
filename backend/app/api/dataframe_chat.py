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

    response = DataFrameSourceResponse.model_validate(source)
    response.table_preview = preview
    return response


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

    response = DataFrameSourceResponse.model_validate(source)
    response.table_preview = preview
    return response


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
