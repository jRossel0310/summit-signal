import { useState } from "react";
import { useAuth } from "../lib/auth";

export default function AuthScreen() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await signup(email, password, code);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <h1 style={{ marginBottom: 4 }}>SummitSignal</h1>
      <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
        {mode === "login" ? "Log in to see your trips." : "Create an account (invite code required)."}
      </p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <input type="email" placeholder="Email" value={email} required
               onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="Password (min 8 chars)" value={password} required
               minLength={8} onChange={(e) => setPassword(e.target.value)} />
        {mode === "signup" && (
          <input type="text" placeholder="Invite code" value={code} required
                 onChange={(e) => setCode(e.target.value)} />
        )}
        {error && <div className="error-note">{error}</div>}
        <button className="btn primary" disabled={busy} type="submit">
          {busy ? "..." : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
      <button className="btn ghost small" style={{ marginTop: 10 }}
              onClick={() => { setError(null); setMode(mode === "login" ? "signup" : "login"); }}>
        {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
      </button>
    </div>
  );
}
