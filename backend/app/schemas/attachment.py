from datetime import datetime

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: int
    user_id: int
    thread_id: int
    original_filename: str
    mime_type: str
    file_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
