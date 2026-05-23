from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import tool
except ImportError:  # pragma: no cover - compatibility fallback
    from langchain.prompts import ChatPromptTemplate
    from langchain.tools import tool

from app.core.config import settings

Board = list[list[str | None]]

PLAYER = "X"
AI = "O"

WIN_LINES: list[list[tuple[int, int]]] = [
    [(0, 0), (0, 1), (0, 2)],
    [(1, 0), (1, 1), (1, 2)],
    [(2, 0), (2, 1), (2, 2)],
    [(0, 0), (1, 0), (2, 0)],
    [(0, 1), (1, 1), (2, 1)],
    [(0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]

MOVE_PREFERENCE: list[tuple[int, int]] = [
    (1, 1),
    (0, 0),
    (0, 2),
    (2, 0),
    (2, 2),
    (0, 1),
    (1, 0),
    (1, 2),
    (2, 1),
]


def _winner_or_none(board: Board) -> str | None:
    for line in WIN_LINES:
        values = [board[r][c] for r, c in line]
        if values[0] and values[0] == values[1] == values[2]:
            return values[0]
    return None


def _is_draw(board: Board) -> bool:
    return all(cell is not None for row in board for cell in row)


def _empty_cells(board: Board) -> list[tuple[int, int]]:
    return [(r, c) for r in range(3) for c in range(3) if board[r][c] is None]


def _board_to_text(board: Board) -> str:
    lines: list[str] = []
    for row in board:
        lines.append(" | ".join(cell if cell is not None else "_" for cell in row))
    return "\n".join(lines)


def _winning_moves(board: Board, symbol: str) -> list[tuple[int, int]]:
    moves: list[tuple[int, int]] = []
    for r, c in _empty_cells(board):
        board[r][c] = symbol
        if _winner_or_none(board) == symbol:
            moves.append((r, c))
        board[r][c] = None
    return moves


def _minimax(board: Board, is_maximizing: bool, depth: int) -> int:
    winner = _winner_or_none(board)
    if winner == AI:
        return 10 - depth
    if winner == PLAYER:
        return depth - 10
    if _is_draw(board):
        return 0

    if is_maximizing:
        best = -100
        for r, c in _empty_cells(board):
            board[r][c] = AI
            score = _minimax(board, False, depth + 1)
            board[r][c] = None
            best = max(best, score)
        return best

    best = 100
    for r, c in _empty_cells(board):
        board[r][c] = PLAYER
        score = _minimax(board, True, depth + 1)
        board[r][c] = None
        best = min(best, score)
    return best


def _sort_by_preference(moves: list[tuple[int, int]]) -> list[tuple[int, int]]:
    order = {move: i for i, move in enumerate(MOVE_PREFERENCE)}
    return sorted(moves, key=lambda mv: order.get(mv, 999))


def _deterministic_best_move(board: Board) -> tuple[tuple[int, int], str]:
    wins = _sort_by_preference(_winning_moves(board, AI))
    if wins:
        return wins[0], "win"

    blocks = _sort_by_preference(_winning_moves(board, PLAYER))
    if blocks:
        return blocks[0], "block"

    cells = _empty_cells(board)
    if not cells:
        raise ValueError("No available moves for AI.")

    best_score = -100
    best_moves: list[tuple[int, int]] = []
    for r, c in cells:
        board[r][c] = AI
        score = _minimax(board, False, 1)
        board[r][c] = None
        if score > best_score:
            best_score = score
            best_moves = [(r, c)]
        elif score == best_score:
            best_moves.append((r, c))

    preferred = _sort_by_preference(best_moves)[0]
    if preferred == (1, 1):
        return preferred, "center"
    if preferred in {(0, 0), (0, 2), (2, 0), (2, 2)}:
        return preferred, "corner"
    return preferred, "minimax"


@tool("check_winner")
def check_winner_tool(board: Board) -> str:
    """Return X, O, draw, or none for a Tic Tac Toe board."""
    winner = _winner_or_none(board)
    if winner:
        return winner
    return "draw" if _is_draw(board) else "none"


@tool("available_moves")
def available_moves_tool(board: Board) -> list[tuple[int, int]]:
    """Return empty board cell positions as (row, col)."""
    return _empty_cells(board)


@tool("validate_move")
def validate_move_tool(board: Board, row: int, col: int) -> bool:
    """Return True only when row/col are in range and the cell is empty."""
    return row in range(3) and col in range(3) and board[row][col] is None


@tool("apply_move")
def apply_move_tool(board: Board, row: int, col: int, symbol: str) -> Board:
    """Apply one move and return a new board. Raises if move is invalid."""
    if symbol not in {PLAYER, AI}:
        raise ValueError("Symbol must be X or O.")
    if not validate_move_tool.invoke({"board": board, "row": row, "col": col}):
        raise ValueError("Invalid move.")
    next_board = copy.deepcopy(board)
    next_board[row][col] = symbol
    return next_board


class LlmMoveChoice(BaseModel):
    row: int = Field(ge=0, le=2)
    col: int = Field(ge=0, le=2)
    reasoning: str = Field(min_length=8)
    strategy: str


@dataclass
class AgentDecision:
    row: int
    col: int
    reasoning: str


class TicTacToeLangChainAgent:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.LITELLM_API_KEY,
            base_url=f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1",
        )
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Tic Tac Toe agent for the O player. "
                    "Choose one legal move and explain briefly. Priorities: "
                    "1) winning move, 2) block X winning move, 3) center, 4) corner, 5) best minimax move.",
                ),
                (
                    "human",
                    "Board matrix: {board_matrix}\n"
                    "Board view:\n{board_text}\n\n"
                    "Available moves: {available_moves}\n"
                    "Immediate O winning moves: {winning_moves}\n"
                    "Immediate X blocking moves: {blocking_moves}\n"
                    "Deterministic best move: {deterministic_move}\n"
                    "Deterministic strategy: {deterministic_strategy}\n\n"
                    "Return row, col, strategy, and reasoning.",
                ),
            ]
        )
        self._chain = self._prompt | self._llm.with_structured_output(LlmMoveChoice)

    async def decide_move(self, board: Board) -> AgentDecision:
        available = available_moves_tool.invoke({"board": board})
        if not available:
            raise ValueError("No available moves for AI.")

        deterministic_move, deterministic_strategy = _deterministic_best_move(board)
        winning_moves = _winning_moves(board, AI)
        blocking_moves = _winning_moves(board, PLAYER)

        llm_choice: LlmMoveChoice | None = None
        try:
            llm_choice = await asyncio.to_thread(
                self._chain.invoke,
                {
                    "board_matrix": board,
                    "board_text": _board_to_text(board),
                    "available_moves": available,
                    "winning_moves": winning_moves,
                    "blocking_moves": blocking_moves,
                    "deterministic_move": deterministic_move,
                    "deterministic_strategy": deterministic_strategy,
                },
            )
        except Exception:
            llm_choice = None

        chosen_move = deterministic_move
        reasoning_parts: list[str] = []

        if llm_choice is not None:
            suggested = (llm_choice.row, llm_choice.col)
            is_valid = validate_move_tool.invoke(
                {"board": board, "row": suggested[0], "col": suggested[1]}
            )
            if is_valid:
                chosen_move = suggested
                reasoning_parts.append(llm_choice.reasoning.strip())
            else:
                reasoning_parts.append(
                    "LLM suggestion was invalid, so deterministic game evaluation selected a legal move."
                )

        if chosen_move != deterministic_move:
            candidate_board = apply_move_tool.invoke(
                {
                    "board": board,
                    "row": chosen_move[0],
                    "col": chosen_move[1],
                    "symbol": AI,
                }
            )
            deterministic_board = apply_move_tool.invoke(
                {
                    "board": board,
                    "row": deterministic_move[0],
                    "col": deterministic_move[1],
                    "symbol": AI,
                }
            )
            candidate_score = _minimax(candidate_board, False, 1)
            deterministic_score = _minimax(deterministic_board, False, 1)
            if candidate_score < deterministic_score:
                chosen_move = deterministic_move
                reasoning_parts.append(
                    "Deterministic minimax guardrail overrode the LLM to preserve optimal play."
                )

        if not reasoning_parts:
            strategy_text = deterministic_strategy.replace("_", " ")
            reasoning_parts.append(
                f"Selected move using deterministic {strategy_text} strategy with minimax fallback."
            )

        if chosen_move == deterministic_move and llm_choice is not None:
            reasoning_parts.append(
                f"Final move aligns with deterministic {deterministic_strategy} priority."
            )

        return AgentDecision(
            row=chosen_move[0],
            col=chosen_move[1],
            reasoning=" ".join(reasoning_parts).strip(),
        )


tic_tac_toe_langchain_agent = TicTacToeLangChainAgent()