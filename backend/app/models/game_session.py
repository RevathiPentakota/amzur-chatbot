import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    game_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    board_state: Mapped[str] = mapped_column(Text, nullable=False, default="null")
    current_turn: Mapped[str] = mapped_column(String(1), nullable=False, default="X")
    winner: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_game_over: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", backref="game_sessions")

    @property
    def board(self) -> list[list[str | None]]:
        return json.loads(self.board_state)

    @board.setter
    def board(self, value: list[list[str | None]]) -> None:
        self.board_state = json.dumps(value)
