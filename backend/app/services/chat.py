"""Chat service using LiteLLM proxy."""
from app.core.config import settings


class ChatService:
    def process_message(self, message: str) -> str:
        """Process user message and return AI response."""
        import litellm

        try:
            # Call LiteLLM proxy using OpenAI-compatible routing.
            response = litellm.completion(
                model=settings.LLM_MODEL,
                api_base=settings.LITELLM_PROXY_URL,
                api_key=settings.LITELLM_API_KEY,
                messages=[{"role": "user", "content": message}],
            )
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Chat service error: {str(e)}")


def get_chat_service() -> ChatService:
    """Dependency for chat service."""
    return ChatService()
