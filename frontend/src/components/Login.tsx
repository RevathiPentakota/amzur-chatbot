import { useState } from "react";

import { googleLoginUrl, loginUser, registerUser } from "../lib/api";

import "./Login.css";

interface LoginProps {
  onAuthenticated: () => void;
}

export function Login({ onAuthenticated }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!email || !password) {
      setError("Email and password are required");
      return;
    }

    setLoading(true);
    setError("");

    try {
      if (mode === "login") {
        await loginUser({ email, password });
      } else {
        await registerUser({ email, password });
      }
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <h1>amzur chatbot</h1>
        <p>Sign in to continue your conversations</p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Enter your password"
        />

        {error && <div className="login-error">{error}</div>}

        <button onClick={submit} disabled={loading} className="login-btn">
          {loading ? "Please wait..." : mode === "login" ? "Login" : "Register"}
        </button>

        <button
          type="button"
          className="login-btn"
          onClick={() => {
            window.location.href = googleLoginUrl();
          }}
          disabled={loading}
        >
          Login with Google
        </button>

        <button
          type="button"
          className="login-mode-btn"
          onClick={() => setMode((prev) => (prev === "login" ? "register" : "login"))}
          disabled={loading}
        >
          {mode === "login" ? "Need an account? Register" : "Already have an account? Login"}
        </button>
      </div>
    </div>
  );
}
