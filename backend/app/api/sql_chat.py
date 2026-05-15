from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.sql_chat import SqlChatRequest, SqlChatResponse
from app.services.auth_service import get_current_user
from app.services.sql_chat_service import sql_chat_service

router = APIRouter(prefix="/sql", tags=["sql"])


@router.post("/chat", response_model=SqlChatResponse)
async def sql_chat(
    request: SqlChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SqlChatResponse:
    try:
        result = await sql_chat_service.ask(db, current_user, request.thread_id, request.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return SqlChatResponse(sql=result.sql, result=result.result, answer=result.answer)
