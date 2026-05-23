from datetime import datetime

from pydantic import BaseModel


class DataFrameSourceResponse(BaseModel):
    id: int
    file_id: int
    user_id: int
    thread_id: int
    filename: str
    file_type: str
    mime_type: str
    file_url: str
    file_path: str
    source_type: str
    google_sheet_id: str | None = None
    worksheet_name: str | None = None
    created_at: datetime
    table_preview: list[dict[str, object | None]] = []

    model_config = {"from_attributes": True}


class GoogleSheetConnectRequest(BaseModel):
    thread_id: int
    sheet: str
    worksheet_name: str | None = None


class DataFrameChatRequest(BaseModel):
    thread_id: int
    question: str


class DataFrameChatResponse(BaseModel):
    answer: str
    intermediate_steps: str
    table_preview: list[dict[str, object | None]]
