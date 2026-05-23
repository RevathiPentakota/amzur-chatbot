import { useState, useCallback } from "react";
import { newTicTacToeGame, makeTicTacToeMove } from "../lib/api";
import type { TicTacToeBoard } from "../types";

type GameStatus = "idle" | "playing" | "win" | "lose" | "draw";

interface GameState {
  gameId: string;
  board: TicTacToeBoard;
  currentTurn: "X" | "O";
  winner: string | null;
  aiReasoning: string;
  status: GameStatus;
  statusMessage: string;
}

const EMPTY_BOARD: TicTacToeBoard = [
  [null, null, null],
  [null, null, null],
  [null, null, null],
];

function getStatusMessage(status: GameStatus): string {
  switch (status) {
    case "idle":
      return "Start a new game to play!";
    case "playing":
      return "Your turn — click a cell (you are X)";
    case "win":
      return "You win! 🎉";
    case "lose":
      return "AI wins! Better luck next time.";
    case "draw":
      return "It's a draw!";
  }
}

const CELL_BASE =
  "flex items-center justify-center w-24 h-24 text-4xl font-bold rounded-xl cursor-pointer select-none transition-all duration-150 ";
const CELL_EMPTY =
  "bg-slate-700 hover:bg-slate-600 hover:scale-105 active:scale-95 text-transparent";
const CELL_X = "bg-indigo-600 text-white cursor-default shadow-lg shadow-indigo-500/30";
const CELL_O = "bg-rose-600 text-white cursor-default shadow-lg shadow-rose-500/30";

function cellClass(cell: string | null, gameOver: boolean): string {
  if (cell === "X") return CELL_BASE + CELL_X;
  if (cell === "O") return CELL_BASE + CELL_O;
  return CELL_BASE + CELL_EMPTY + (gameOver ? " opacity-50 cursor-not-allowed" : "");
}

export function TicTacToe() {
  const [game, setGame] = useState<GameState>({
    gameId: "",
    board: EMPTY_BOARD,
    currentTurn: "X",
    winner: null,
    aiReasoning: "",
    status: "idle",
    statusMessage: getStatusMessage("idle"),
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startGame = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await newTicTacToeGame();
      setGame({
        gameId: res.game_id,
        board: res.board,
        currentTurn: res.current_turn as "X" | "O",
        winner: null,
        aiReasoning: "",
        status: "playing",
        statusMessage: getStatusMessage("playing"),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start game.");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCellClick = useCallback(
    async (row: number, col: number) => {
      if (
        game.status !== "playing" ||
        loading ||
        game.board[row][col] !== null ||
        !game.gameId
      ) {
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const res = await makeTicTacToeMove({ game_id: game.gameId, row, col });

        let status: GameStatus = "playing";
        if (res.game_over) {
          if (res.winner === "X") status = "win";
          else if (res.winner === "O") status = "lose";
          else status = "draw";
        }

        setGame((prev) => ({
          ...prev,
          board: res.board,
          currentTurn: res.current_turn as "X" | "O",
          winner: res.winner,
          aiReasoning: res.ai_reasoning ?? "",
          status,
          statusMessage: getStatusMessage(status),
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Move failed.");
      } finally {
        setLoading(false);
      }
    },
    [game, loading],
  );

  const isGameOver = game.status !== "playing" && game.status !== "idle";

  const statusColors: Record<GameStatus, string> = {
    idle: "text-slate-400",
    playing: "text-indigo-300",
    win: "text-emerald-400",
    lose: "text-rose-400",
    draw: "text-amber-400",
  };

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4 py-12">
      {/* Title */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-extrabold text-white tracking-tight mb-1">
          Tic Tac Toe
        </h1>
        <p className="text-slate-400 text-sm">You are X &bull; AI is O &bull; LangChain agent</p>
      </div>

      {/* Status banner */}
      <div
        className={`mb-6 text-lg font-semibold min-h-7 transition-colors duration-300 ${statusColors[game.status]}`}
      >
        {loading && game.status === "playing"
          ? "AI is thinking..."
          : game.statusMessage}
      </div>

      {game.status !== "idle" && (
        <div className="mb-5 text-sm text-slate-300 bg-slate-800/70 border border-slate-700 rounded-xl px-4 py-2">
          {isGameOver
            ? game.winner === "draw"
              ? "Result: Draw"
              : `Winner: ${game.winner}`
            : `Current turn: ${game.currentTurn}`}
        </div>
      )}

      {/* Board */}
      <div className="grid grid-cols-3 gap-3 mb-8">
        {game.board.map((row, rIdx) =>
          row.map((cell, cIdx) => (
            <button
              key={`${rIdx}-${cIdx}`}
              className={cellClass(cell, isGameOver || loading)}
              onClick={() => void handleCellClick(rIdx, cIdx)}
              disabled={isGameOver || loading || cell !== null}
              aria-label={`Row ${rIdx + 1}, Column ${cIdx + 1}: ${cell ?? "empty"}`}
            >
              {cell}
            </button>
          )),
        )}
      </div>

      {/* Controls */}
      <div className="flex flex-col items-center gap-3">
        <button
          onClick={() => void startGame()}
          disabled={loading}
          className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all duration-150 active:scale-95 shadow-lg shadow-indigo-500/30"
        >
          {game.status === "idle" ? "Start Game" : "Restart Game"}
        </button>

        {loading && game.status !== "playing" && (
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <span className="inline-block w-4 h-4 border-2 border-slate-500 border-t-indigo-400 rounded-full animate-spin" />
            Setting up…
          </div>
        )}
      </div>

      {game.aiReasoning && (
        <div className="mt-5 max-w-xl rounded-xl border border-slate-700 bg-slate-800/70 px-4 py-3 text-left">
          <p className="mb-1 text-xs uppercase tracking-wide text-slate-400">AI reasoning</p>
          <p className="text-sm text-slate-200 leading-relaxed">{game.aiReasoning}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="mt-4 text-rose-400 text-sm bg-rose-900/30 border border-rose-700 rounded-lg px-4 py-2 max-w-xs text-center">
          {error}
        </p>
      )}

      {/* Legend */}
      <div className="mt-10 flex gap-6 text-sm text-slate-500">
        <span className="flex items-center gap-2">
          <span className="inline-block w-4 h-4 rounded bg-indigo-600" /> You (X)
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block w-4 h-4 rounded bg-rose-600" /> AI (O)
        </span>
      </div>
    </div>
  );
}
