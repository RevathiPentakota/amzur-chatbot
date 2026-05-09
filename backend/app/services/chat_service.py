from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
import logging

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User


class ChatService:
    async def get_thread_history(
        self,
        db: AsyncSession,
        thread_id: int,
        user_id: int,
        limit: int = 5,
    ) -> list[ChatMessage]:
        """
        Load the last N conversations for a specific thread.
        
        Args:
            db: Database session
            thread_id: Thread ID to fetch history for
            user_id: User ID for validation
            limit: Number of conversation pairs to retrieve (default: 5)
            
        Returns:
            List of ChatMessage records ordered by created_at ascending
        """
        result = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result)
        # Reverse to get chronological order (oldest first)
        return messages[::-1]

    def _convert_to_langchain_messages(self, chat_history: list[ChatMessage]) -> list[BaseMessage]:
        """
        Convert chat history to LangChain message format.
        
        Args:
            chat_history: List of ChatMessage records
            
        Returns:
            List of LangChain HumanMessage and AIMessage objects
        """
        messages: list[BaseMessage] = []
        for chat in chat_history:
            # Add user message
            messages.append(HumanMessage(content=chat.message))
            # Add assistant response
            messages.append(AIMessage(content=chat.response))
        return messages

    async def generate_reply(self, message: str, conversation_history: list[BaseMessage] | None = None) -> str:
        """
        Generate a reply using LLM with optional conversation history.
        
        Args:
            message: Current user message
            conversation_history: Optional list of previous messages in LangChain format
            
        Returns:
            Generated reply from the LLM
        """
        import litellm

        # Build messages list: include history + current message
        messages_to_send = []
        
        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if isinstance(msg, HumanMessage):
                    messages_to_send.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    messages_to_send.append({"role": "assistant", "content": msg.content})
        
        # Add current user message
        messages_to_send.append({"role": "user", "content": message})

        try:
            response = litellm.completion(
                model=settings.LLM_MODEL,
                api_base=settings.LITELLM_PROXY_URL,
                api_key=settings.LITELLM_API_KEY,
                messages=messages_to_send,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logging.exception("LiteLLM request failed")
            raise RuntimeError("LLM provider is unavailable or timed out. Please try again.") from exc

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response. Please try again.")
        return content

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

        # Load the last 5 conversations for this thread
        conversation_history = await self.get_thread_history(
            db, thread_id, user.id, limit=5
        )
        
        # Convert history to LangChain message format
        langchain_messages = self._convert_to_langchain_messages(conversation_history)
        
        # Generate reply with conversation context
        reply = await self.generate_reply(message, langchain_messages)
        
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
