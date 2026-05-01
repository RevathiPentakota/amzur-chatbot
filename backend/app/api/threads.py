from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.thread import ThreadCreateRequest, ThreadResponse, ThreadUpdateRequest
from app.services.auth_service import get_current_user
from app.services.thread_service import thread_service


router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", response_model=ThreadResponse)
async def create_thread(
    payload: ThreadCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    thread = await thread_service.create_thread(db, current_user, payload.title)
    return ThreadResponse.model_validate(thread)


@router.get("", response_model=list[ThreadResponse])
async def list_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThreadResponse]:
    threads = await thread_service.list_threads(db, current_user)
    return [ThreadResponse.model_validate(item) for item in threads]


@router.put("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: int,
    payload: ThreadUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    thread = await thread_service.update_thread_title(db, current_user, thread_id, payload.title)
    return ThreadResponse.model_validate(thread)


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    await thread_service.delete_thread(db, current_user, thread_id)
    return {"message": "Thread deleted"}
