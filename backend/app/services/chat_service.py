from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User


class ChatService:
    async def generate_reply(self, message: str) -> str:
        import litellm

        response = litellm.completion(
            model=settings.LLM_MODEL,
            api_base=settings.LITELLM_PROXY_URL,
            api_key=settings.LITELLM_API_KEY,
            messages=[{"role": "user", "content": message}],
        )
        return response.choices[0].message.content

    @staticmethod
    def auto_title(message: str) -> str:
        words = message.strip().split()
        return " ".join(words[:6]) if words else "New Thread"

    async def chat(self, db: AsyncSession, user: User, message: str, thread_id: int) -> str:
        thread = await db.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise ValueError("Thread not found")

        reply = await self.generate_reply(message)
        db_item = ChatMessage(
            user_id=user.id,
            thread_id=thread.id,
            message=message,
            response=reply,
        )
        db.add(db_item)

        if not thread.title:
            thread.title = self.auto_title(message)

        await db.commit()
        return reply

    async def history(self, db: AsyncSession, user: User) -> list[ChatMessage]:
        result = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result)

    async def history_by_thread(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
    ) -> list[ChatMessage]:
        thread = await db.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise ValueError("Thread not found")

        result = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id, ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result)


chat_service = ChatService()
