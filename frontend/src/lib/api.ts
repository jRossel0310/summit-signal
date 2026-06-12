// Thin typed client for the local FastAPI backend.
import type {
  AppSettings,
  CheckStatus,
  ConditionCheck,
  ConditionCheckDetail,
  SearchResult,
  SettingsUpdate,
  Trip,
  TripCreate,
} from "../types";

export const API_BASE = "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      ...init,
    });
  } catch {
    throw new Error("Backend unreachable. Is the Python server running on port 8000?");
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

  searchLocation: (query: string) =>
    request<{ results: SearchResult[] }>("/search/location", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

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
    const res = await fetch(`${API_BASE}/trips/${tripId}/upload-gpx`, { method: "POST", body: fd });
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

  printReportUrl: (tripId: number, checkId?: number) =>
    `${API_BASE}/trips/${tripId}/print-report${checkId ? `?check_id=${checkId}` : ""}`,

  getSettings: () => request<AppSettings>("/settings"),
  updateSettings: (patch: SettingsUpdate) =>
    request<AppSettings>("/settings", { method: "POST", body: JSON.stringify(patch) }),
  ollamaModels: () =>
    request<{ available: boolean; models: string[] }>("/settings/ollama-models"),

  runAllSavedTrips: () =>
    request<{ started: number[] }>("/agent/run-all-saved-trips", { method: "POST" }),
};

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
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
