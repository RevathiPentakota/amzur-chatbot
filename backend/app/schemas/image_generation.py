from datetime import datetime

from pydantic import BaseModel


class ImageGenerateRequest(BaseModel):
    prompt: str
    thread_id: int | None = None


class ImageGenerateResponse(BaseModel):
    id: int
    image_url: str
    prompt: str
    thread_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
