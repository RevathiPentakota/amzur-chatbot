import base64
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.attachment import Attachment
from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User
from app.services.attachment_service import attachment_service
from app.services.video_service import video_service


class ChatService:
    async def _recent_thread_attachments(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        history_window: int = 20,
    ) -> list[Attachment]:
        """Reuse the most recent attachment set in a thread for follow-up questions."""
        recent_messages = await db.scalars(
            select(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .where(ChatMessage.user_id == user.id, ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(history_window)
        )

        for message in recent_messages:
            if message.attachments:
                return list(message.attachments)

        # If uploads exist but haven't been linked to a chat message yet, include them.
        orphaned_attachments = await db.scalars(
            select(Attachment)
            .where(
                Attachment.user_id == user.id,
                Attachment.thread_id == thread_id,
                Attachment.chat_message_id.is_(None),
            )
            .order_by(Attachment.created_at.desc())
            .limit(5)
        )
        return list(orphaned_attachments)
    @staticmethod
    def _looks_like_attachment_refusal(text: str) -> bool:
        lowered = text.lower()
        refusal_markers = [
            "unable to view",
            "unable to access",
            "unable to interact",
            "can't access",
            "cannot access",
            "can't view",
            "cannot view",
            "cannot interact",
            "i cannot open",
            "i'm unable to open",
            "i am unable to open",
            "don't have the ability to access",
            "do not have the ability to access",
            "share the main content",
            "share the text",
            "key points from the document",
            "provide text from the document",
            "paste the content",
        ]
        return any(marker in lowered for marker in refusal_markers)

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

    @staticmethod
    def _history_as_text(conversation_history: list[BaseMessage] | None) -> str:
        if not conversation_history:
            return ""

        lines: list[str] = []
        for msg in conversation_history:
            if isinstance(msg, HumanMessage):
                lines.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                lines.append(f"Assistant: {msg.content}")
        return "\n".join(lines)

    @staticmethod
    def _build_attachment_context(attachments: list[Attachment]) -> str:
        if not attachments:
            return ""

        chunks: list[str] = []
        for attachment in attachments:
            extracted = attachment_service.read_text_context(attachment)
            if attachment.file_type == "image":
                # Images are passed as multimodal blocks separately.
                continue

            content = extracted.strip() if extracted else "[No readable text extracted from this file]"
            chunks.append(
                f"Attachment: {attachment.original_filename} ({attachment.file_type})\n{content}"
            )

        return "\n\n".join(chunks)

    @staticmethod
    def _image_blocks(attachments: list[Attachment]) -> list[dict[str, object]]:
        blocks: list[dict[str, object]] = []
        for attachment in attachments:
            if attachment.file_type != "image":
                continue

            raw = Path(attachment.file_path).read_bytes()
            encoded = base64.b64encode(raw).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{attachment.mime_type};base64,{encoded}"},
                }
            )
        return blocks

    @staticmethod
    async def _video_frame_blocks(
        attachments: list[Attachment],
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Extract frames from all video attachments and return (image_url blocks, filenames)."""
        import asyncio

        blocks: list[dict[str, object]] = []
        filenames: list[str] = []
        for attachment in attachments:
            if attachment.file_type != "video":
                continue
            video_blocks = await asyncio.to_thread(
                video_service.frames_as_image_blocks,
                attachment.file_path,
                attachment.original_filename,
            )
            if video_blocks:
                blocks.extend(video_blocks)
                filenames.append(attachment.original_filename)
        return blocks, filenames

    async def generate_reply(
        self,
        message: str,
        conversation_history: list[BaseMessage] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str:
        """
        Generate a reply using LLM with optional conversation history.
        
        Args:
            message: Current user message
            conversation_history: Optional list of previous messages in LangChain format
            
        Returns:
            Generated reply from the LLM
        """
        import litellm

        attachment_items = attachments or []
        attachment_context = self._build_attachment_context(attachment_items)

        # Build messages list: include history + current message + optional file context
        messages_to_send = []

        # Always inject a system instruction when documents are present so the model
        # never claims it "cannot access files" — the text is already inline.
        if attachment_items:
            messages_to_send.append(
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. When the user's message contains a "
                        "'--- Document content ---' section, that IS the file content — it has "
                        "already been extracted and embedded inline. Answer based on that text. "
                        "Never say you cannot access, view, or open files or attachments."
                    ),
                }
            )

        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if isinstance(msg, HumanMessage):
                    messages_to_send.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    messages_to_send.append({"role": "assistant", "content": msg.content})

        user_message = message
        if attachment_context:
            # Present extracted text as inline content, not as a named "attachment",
            # to avoid triggering the model's "I cannot access files" response.
            user_message = (
                f"{message}\n\n"
                f"--- Document content ---\n{attachment_context}\n--- End of document content ---"
            )

        # Collect visual content: direct images + extracted video frames.
        image_blocks = self._image_blocks(attachment_items)
        video_blocks, video_filenames = await self._video_frame_blocks(attachment_items)
        all_visual_blocks = image_blocks + video_blocks

        model_to_use = settings.LLM_MODEL
        if all_visual_blocks:
            model_to_use = settings.VISION_MODEL
            history_text = self._history_as_text(conversation_history)

            video_note = ""
            if video_filenames:
                names = ", ".join(video_filenames)
                n = len(video_blocks)
                video_note = (
                    f"\n\nNote: The following {n} image(s) are key frames extracted "
                    f"automatically from the uploaded video file(s): {names}. "
                    "Analyse the visual content of those frames to answer the user."
                )

            multimodal_text = (
                (f"Conversation history:\n{history_text}\n\n" if history_text else "")
                + f"User message:\n{message}"
                + (
                    f"\n\n--- Document content ---\n{attachment_context}\n--- End of document content ---"
                    if attachment_context
                    else ""
                )
                + video_note
            )
            messages_to_send = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": multimodal_text}, *all_visual_blocks],
                }
            ]
        else:
            messages_to_send.append({"role": "user", "content": user_message})

        timeout_attempts = [
            int(settings.LLM_TIMEOUT_SECONDS),
            int(settings.LLM_TIMEOUT_SECONDS * 1.5),
            int(settings.LLM_TIMEOUT_SECONDS * 2),
        ]
        last_exc: Exception | None = None
        response = None
        for idx, timeout_value in enumerate(timeout_attempts):
            try:
                logging.info(
                    "LiteLLM attempt %s/%s: model=%s, timeout=%ds",
                    idx + 1,
                    len(timeout_attempts),
                    model_to_use,
                    timeout_value,
                )
                import asyncio
                response = await asyncio.to_thread(
                    litellm.completion,
                    model=model_to_use,
                    api_base=settings.LITELLM_PROXY_URL,
                    api_key=settings.LITELLM_API_KEY,
                    messages=messages_to_send,
                    timeout=timeout_value,
                )
                logging.info("LiteLLM success on attempt %s", idx + 1)
                break
            except Exception as exc:
                last_exc = exc
                logging.warning(
                    "LiteLLM failed attempt %s: %s: %s",
                    idx + 1,
                    type(exc).__name__,
                    str(exc)[:200],
                )

        if response is None:
            raise RuntimeError("LLM provider is unavailable or timed out. Please try again.") from last_exc

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response. Please try again.")
        return content

    @staticmethod
    def auto_title(message: str) -> str:
        words = message.strip().split()
        return " ".join(words[:6]) if words else "New Thread"

    async def chat(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        thread_id: int,
        attachment_ids: list[int] | None = None,
    ) -> str:
        thread = await db.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise ValueError("Thread not found")

        attachments = await attachment_service.resolve_for_chat(
            db, user, thread_id, attachment_ids
        )

        # For follow-up questions in the same thread, reuse the most recent
        # attachment context when the client omits attachment_ids.
        if not attachments and not attachment_ids:
            attachments = await self._recent_thread_attachments(db, user, thread_id)

        # Load the last 5 conversations for this thread
        conversation_history = await self.get_thread_history(
            db, thread_id, user.id, limit=5
        )
        
        # Convert history to LangChain message format
        langchain_messages = self._convert_to_langchain_messages(conversation_history)

        # Generate reply with conversation context. If LLM times out for attachment chats,
        # return extracted text instead of failing the whole request.
        try:
            reply = await self.generate_reply(message, langchain_messages, attachments)
        except RuntimeError:
            if attachments:
                extracted_context = self._build_attachment_context(attachments)
                if extracted_context.strip():
                    reply = (
                        "The AI provider timed out, so here is the content extracted from your uploaded file:\n\n"
                        f"{extracted_context[:2400]}"
                    )
                else:
                    reply = (
                        "The AI provider timed out, and no readable text could be extracted from the uploaded file. "
                        "Please try again or upload a text-based file."
                    )
            else:
                raise

        # Safety net: if the model still claims it cannot access the file, skip the LLM
        # entirely and return the extracted text directly.
        if attachments and self._looks_like_attachment_refusal(reply):
            extracted_context = self._build_attachment_context(attachments)
            if extracted_context.strip():
                reply = (
                    "Here is the content extracted from the uploaded file:\n\n"
                    f"{extracted_context[:2400]}"
                )
            else:
                reply = (
                    "I received the attachment, but no readable text could be extracted from it. "
                    "Please try a text-based file (PDF with selectable text, DOCX, TXT, CSV) "
                    "or paste the content directly into the chat."
                )

        db_item = ChatMessage(
            user_id=user.id,
            thread_id=thread.id,
            message=message,
            response=reply,
        )
        db.add(db_item)
        await db.flush()

        attachment_service.link_to_chat_message(attachments, db_item)

        if not thread.title:
            thread.title = self.auto_title(message)

        await db.commit()
        return reply

    async def history(self, db: AsyncSession, user: User) -> list[ChatMessage]:
        result = await db.scalars(
            select(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result)

    async def history_by_thread(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
    ) -> tuple[list[ChatMessage], list]:
        from app.models.generated_image import GeneratedImage
        
        thread = await db.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise ValueError("Thread not found")

        # Load messages with attachments
        messages = await db.scalars(
            select(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .where(ChatMessage.user_id == user.id, ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc())
        )
        
        # Load generated images for the thread
        images = await db.scalars(
            select(GeneratedImage)
            .where(GeneratedImage.thread_id == thread_id, GeneratedImage.user_id == user.id)
            .order_by(GeneratedImage.created_at.asc())
        )
        
        return list(messages), list(images)


chat_service = ChatService()
