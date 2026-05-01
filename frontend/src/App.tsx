import { useEffect, useState } from "react";

import { Chat } from "./components/Chat";
import { Login } from "./components/Login";
import { getThreads } from "./lib/api";

import "./App.css";

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

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

  return <Chat />;
}

export default App;
