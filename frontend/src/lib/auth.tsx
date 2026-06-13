import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "../types";
import { api, getToken, setToken } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("summitsignal-unauthorized", onUnauthorized);
    return () => window.removeEventListener("summitsignal-unauthorized", onUnauthorized);
  }, []);

  async function login(email: string, password: string) {
    const { token, user } = await api.login(email, password);
    setToken(token); setUser(user);
  }
  async function signup(email: string, password: string, code: string) {
    const { token, user } = await api.signup(email, password, code);
    setToken(token); setUser(user);
  }
  function logout() { setToken(null); setUser(null); }

  return (
    <AuthContext.Provider value={{ user, ready, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
