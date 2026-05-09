from datetime import datetime

from pydantic import BaseModel


class RagUploadResponse(BaseModel):
    id: int
    user_id: int
    thread_id: int
    filename: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RagChatRequest(BaseModel):
    thread_id: int
    question: str


class RagChatResponse(BaseModel):
    answer: str
    thread_id: int


class RagPdfItem(BaseModel):
    id: int
    user_id: int
    thread_id: int
    filename: str
    created_at: datetime

    model_config = {"from_attributes": True}
