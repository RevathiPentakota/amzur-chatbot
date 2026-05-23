import { useEffect, useState } from "react";

import { Chat } from "./components/Chat";
import { Login } from "./components/Login";
import { TicTacToe } from "./components/TicTacToe";
import { getThreads } from "./lib/api";

import "./App.css";

type AppView = "chat" | "tictactoe";

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<AppView>("chat");

  useEffect(() => {
    const checkSession = async () => {
      try {
        await getThreads();
        setAuthenticated(true);
      } catch {
        setAuthenticated(false);
      } finally {
        setCheckingSession(false);
      }
    };

    void checkSession();
  }, []);

  if (checkingSession) {
    return null;
  }

  if (!authenticated) {
    return <Login onAuthenticated={() => setAuthenticated(true)} />;
  }

  return (
    <div className="flex flex-col h-screen bg-slate-900">
      {/* Top navigation bar */}
      <nav className="flex items-center gap-1 px-4 py-2 bg-slate-800 border-b border-slate-700 shrink-0">
        <button
          onClick={() => setView("chat")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            view === "chat"
              ? "bg-indigo-600 text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-700"
          }`}
        >
          Chat
        </button>
        <button
          onClick={() => setView("tictactoe")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            view === "tictactoe"
              ? "bg-indigo-600 text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-700"
          }`}
        >
          Tic Tac Toe
        </button>
      </nav>

      {/* Main content */}
      <div className="flex-1 min-h-0 overflow-auto">
        {view === "chat" ? <Chat /> : <TicTacToe />}
      </div>
    </div>
  );
}

export default App;
