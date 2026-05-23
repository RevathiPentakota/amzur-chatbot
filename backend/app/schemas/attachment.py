from datetime import datetime

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: int
    file_id: int | None = None
    user_id: int
    thread_id: int
    original_filename: str
    filename: str | None = None
    mime_type: str
    file_type: str
    file_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
