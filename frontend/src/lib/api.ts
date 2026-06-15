// Thin typed client for the FastAPI backend.
import type {
  AppSettings,
  CheckStatus,
  ConditionCheck,
  ConditionCheckDetail,
  SearchResult,
  SettingsUpdate,
  Trip,
  TripCreate,
  User,
} from "../types";
import type { SelectionResult } from "../layers/types";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const TOKEN_KEY = "summitsignal_token";
export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers || {}),
      },
      ...init,
    });
  } catch {
    throw new Error("Backend unreachable. Is the server running?");
  }
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("summitsignal-unauthorized"));
    throw new Error("Your session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  signup: (email: string, password: string, invite_code: string) =>
    request<{ token: string; user: User }>("/auth/signup", {
      method: "POST", body: JSON.stringify({ email, password, invite_code }) }),
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<User>("/auth/me"),

  searchLocation: (query: string) =>
    request<{ results: SearchResult[] }>("/search/location", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  pointContext: (lat: number, lon: number, layers?: string[]) => {
    const q = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    if (layers && layers.length) q.set("layers", layers.join(","));
    return request<SelectionResult>(`/map/point-context?${q.toString()}`);
  },

  listTrips: () => request<Trip[]>("/trips"),
  getTrip: (id: number) => request<Trip>(`/trips/${id}`),
  createTrip: (t: TripCreate) =>
    request<Trip>("/trips", { method: "POST", body: JSON.stringify(t) }),
  updateTrip: (id: number, patch: Partial<TripCreate>) =>
    request<Trip>(`/trips/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteTrip: (id: number) => request<{ deleted: boolean }>(`/trips/${id}`, { method: "DELETE" }),

  uploadGpx: async (tripId: number, file: File): Promise<Trip> => {
    const fd = new FormData();
    fd.append("file", file);
    const token = getToken();
    const res = await fetch(`${API_BASE}/trips/${tripId}/upload-gpx`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail || `GPX upload failed (${res.status})`);
    }
    return res.json();
  },

  runConditionCheck: (tripId: number) =>
    request<ConditionCheck>(`/trips/${tripId}/run-condition-check`, { method: "POST" }),
  listChecks: (tripId: number) => request<ConditionCheck[]>(`/trips/${tripId}/checks`),
  getCheck: (id: number) => request<ConditionCheckDetail>(`/condition-checks/${id}`),
  getCheckStatus: (id: number) => request<CheckStatus>(`/condition-checks/${id}/status`),
  generateSummary: (id: number) =>
    request<{ summary_text: string; generator: string }>(
      `/condition-checks/${id}/generate-summary`,
      { method: "POST" },
    ),

  fetchReportHtml: async (tripId: number, checkId?: number): Promise<string> => {
    const q = checkId ? `?check_id=${checkId}` : "";
    const token = getToken();
    const res = await fetch(`${API_BASE}/trips/${tripId}/print-report${q}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Report failed (${res.status})`);
    return res.text();
  },

  getSettings: () => request<AppSettings>("/settings"),
  updateSettings: (patch: SettingsUpdate) =>
    request<AppSettings>("/settings", { method: "POST", body: JSON.stringify(patch) }),

  runAllSavedTrips: () =>
    request<{ started: number[] }>("/agent/run-all-saved-trips", { method: "POST" }),
};

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ageLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
