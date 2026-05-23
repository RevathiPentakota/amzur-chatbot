from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.tic_tac_toe import MakeMoveRequest, MakeMoveResponse, NewGameResponse
from app.services.auth_service import get_current_user
from app.services.tic_tac_toe_service import tic_tac_toe_service

router = APIRouter(prefix="/tic-tac-toe", tags=["tic-tac-toe"])


@router.post("/new", response_model=NewGameResponse)
async def new_game(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NewGameResponse:
    game = await tic_tac_toe_service.new_game(db, current_user)
    return NewGameResponse(
        game_id=game.game_id,
        board=game.board,
        current_turn=game.current_turn,
    )


@router.post("/move", response_model=MakeMoveResponse)
async def make_move(
    payload: MakeMoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MakeMoveResponse:
    try:
        result = await tic_tac_toe_service.make_move(
            db, payload.game_id, payload.row, payload.col, current_user
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MakeMoveResponse(
        board=result.board,
        player_move=result.player_move,
        ai_move=result.ai_move,
        ai_reasoning=result.ai_reasoning,
        winner=result.winner,
        game_over=result.game_over,
        current_turn=result.current_turn,
    )
