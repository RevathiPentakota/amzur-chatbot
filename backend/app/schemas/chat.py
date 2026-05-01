from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: int


class ChatResponse(BaseModel):
    reply: str
    thread_id: int


class ChatHistoryItem(BaseModel):
    id: int
    thread_id: int
    message: str
    response: str
    created_at: datetime

    model_config = {"from_attributes": True}
