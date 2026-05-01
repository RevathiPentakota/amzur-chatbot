from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User


class ThreadService:
    async def create_thread(
        self,
        db: AsyncSession,
        user: User,
        title: str | None = None,
    ) -> Thread:
        thread = Thread(user_id=user.id, title=title.strip() if title else None)
        db.add(thread)
        await db.commit()
        await db.refresh(thread)
        return thread

    async def list_threads(self, db: AsyncSession, user: User) -> list[Thread]:
        result = await db.scalars(
            select(Thread)
            .where(Thread.user_id == user.id)
            .order_by(Thread.updated_at.desc(), Thread.created_at.desc())
        )
        return list(result)

    async def get_thread(self, db: AsyncSession, user: User, thread_id: int) -> Thread:
        thread = await db.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread

    async def update_thread_title(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        title: str,
    ) -> Thread:
        thread = await self.get_thread(db, user, thread_id)
        thread.title = title.strip() or None
        await db.commit()
        await db.refresh(thread)
        return thread

    async def delete_thread(self, db: AsyncSession, user: User, thread_id: int) -> None:
        thread = await self.get_thread(db, user, thread_id)
        await db.execute(delete(ChatMessage).where(ChatMessage.thread_id == thread.id))
        await db.delete(thread)
        await db.commit()


thread_service = ThreadService()
