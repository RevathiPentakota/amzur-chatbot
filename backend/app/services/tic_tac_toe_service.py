"""Tic Tac Toe service using a LangChain-powered AI agent."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tic_tac_toe_agent import (
    AI,
    PLAYER,
    apply_move_tool,
    check_winner_tool,
    tic_tac_toe_langchain_agent,
    validate_move_tool,
)
from app.models.game_session import GameSession
from app.models.user import User

Board = list[list[str | None]]


def _empty_board() -> Board:
    return [[None, None, None], [None, None, None], [None, None, None]]


@dataclass
class MoveResult:
    board: Board
    player_move: str
    ai_move: Optional[str]
    ai_reasoning: Optional[str]
    winner: Optional[str]
    game_over: bool
    current_turn: str


class TicTacToeService:
    async def new_game(self, db: AsyncSession, user: User) -> GameSession:
        board = _empty_board()
        session = GameSession(
            game_id=str(uuid.uuid4()),
            user_id=user.id,
            current_turn=PLAYER,
            winner=None,
            is_game_over=False,
        )
        session.board = board
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_game(self, db: AsyncSession, game_id: str, user: User) -> GameSession | None:
        result = await db.execute(
            select(GameSession).where(
                GameSession.game_id == game_id,
                GameSession.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def make_move(
        self,
        db: AsyncSession,
        game_id: str,
        row: int,
        col: int,
        user: User,
    ) -> MoveResult:
        if row not in range(3) or col not in range(3):
            raise ValueError("Row and col must be between 0 and 2.")

        game = await self.get_game(db, game_id, user)
        if game is None:
            raise LookupError("Game not found.")
        if game.is_game_over:
            raise ValueError("Game is already over.")
        if game.current_turn != PLAYER:
            raise ValueError("It is not the player's turn.")

        board = game.board
        if not validate_move_tool.invoke({"board": board, "row": row, "col": col}):
            raise ValueError("Cell is already occupied.")

        # Apply player move
        board = apply_move_tool.invoke({"board": board, "row": row, "col": col, "symbol": PLAYER})
        player_move_str = f"({row},{col})"

        winner_state = check_winner_tool.invoke({"board": board})
        ai_move_str: str | None = None
        ai_reasoning: str | None = None

        if winner_state != "none":
            game.board = board
            game.winner = winner_state
            game.is_game_over = True
            game.current_turn = PLAYER
            await db.commit()
            return MoveResult(
                board=board,
                player_move=player_move_str,
                ai_move=None,
                ai_reasoning="No AI move required because the game ended after the player's move.",
                winner=game.winner,
                game_over=True,
                current_turn=game.current_turn,
            )

        # AI move via LangChain agent with deterministic guardrails.
        ai_decision = await tic_tac_toe_langchain_agent.decide_move(board)
        board = apply_move_tool.invoke(
            {
                "board": board,
                "row": ai_decision.row,
                "col": ai_decision.col,
                "symbol": AI,
            }
        )
        ai_move_str = f"({ai_decision.row},{ai_decision.col})"
        ai_reasoning = ai_decision.reasoning

        winner_state = check_winner_tool.invoke({"board": board})

        game.board = board
        if winner_state != "none":
            game.winner = winner_state
            game.is_game_over = True
            game.current_turn = PLAYER
        else:
            game.winner = None
            game.is_game_over = False
            game.current_turn = PLAYER

        await db.commit()

        return MoveResult(
            board=board,
            player_move=player_move_str,
            ai_move=ai_move_str,
            ai_reasoning=ai_reasoning,
            winner=game.winner,
            game_over=game.is_game_over,
            current_turn=game.current_turn,
        )


tic_tac_toe_service = TicTacToeService()
