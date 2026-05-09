from datetime import datetime

from pydantic import BaseModel

from app.schemas.attachment import AttachmentResponse


class ChatRequest(BaseModel):
    message: str
    thread_id: int
    attachment_ids: list[int] | None = None


class ChatResponse(BaseModel):
    reply: str
    thread_id: int


class ChatHistoryItem(BaseModel):
    id: int
    thread_id: int
    message: str
    response: str
    created_at: datetime
    attachments: list[AttachmentResponse] = []

    model_config = {"from_attributes": True}
