from pydantic import BaseModel


class NewGameResponse(BaseModel):
    game_id: str
    board: list[list[str | None]]
    current_turn: str


class MakeMoveRequest(BaseModel):
    game_id: str
    row: int
    col: int


class MakeMoveResponse(BaseModel):
    board: list[list[str | None]]
    player_move: str
    ai_move: str | None
    ai_reasoning: str | None
    winner: str | None
    game_over: bool
    current_turn: str