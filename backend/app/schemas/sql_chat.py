from pydantic import BaseModel


class SqlChatRequest(BaseModel):
    question: str
    thread_id: int


class SqlChatResponse(BaseModel):
    sql: str
    result: list[dict[str, object | None]]
    answer: str
