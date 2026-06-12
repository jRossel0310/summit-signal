import { useEffect, useState } from "react";
import type { AppSettings, SettingsUpdate } from "../types";
import { CONNECTOR_LABELS } from "../types";
import { api } from "../lib/api";

interface Props {
  onSaved: (s: AppSettings) => void;
}

const KEYED = [
  { id: "firms", label: "NASA FIRMS map key", url: "https://firms.modaps.eosdis.nasa.gov/api/map_key/" },
  { id: "airnow", label: "AirNow API key", url: "https://docs.airnowapi.org/account/request/" },
  { id: "nps", label: "NPS API key", url: "https://www.nps.gov/subjects/developer/get-started.htm" },
];

export default function SettingsView({ onSaved }: Props) {
  const [s, setS] = useState<AppSettings | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaAvailable, setOllamaAvailable] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setS).catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    if (!s?.ollama_enabled) return;
    api.ollamaModels()
      .then((r) => { setOllamaAvailable(r.available); setOllamaModels(r.models); })
      .catch(() => setOllamaAvailable(false));
  }, [s?.ollama_enabled, s?.ollama_url]);

  if (error && !s) return <div className="settings-page"><div className="error-note">{error}</div></div>;
  if (!s) return <div className="settings-page"><div className="empty-note">Loading settings…</div></div>;

  function patch<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setS((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function save() {
    if (!s) return;
    setSaving(true);
    setError(null);
    try {
      const payload: SettingsUpdate = {
        fire_radius_miles: s.fire_radius_miles,
        aqi_moderate_threshold: s.aqi_moderate_threshold,
        aqi_major_threshold: s.aqi_major_threshold,
        wind_gust_moderate_mph: s.wind_gust_moderate_mph,
        wind_gust_major_mph: s.wind_gust_major_mph,
        precip_prob_moderate: s.precip_prob_moderate,
        cold_low_f: s.cold_low_f,
        stale_hours: s.stale_hours,
        connectors_enabled: s.connectors_enabled,
        ollama_enabled: s.ollama_enabled,
        ollama_url: s.ollama_url,
        ollama_model: s.ollama_model,
        schedule_hours: s.schedule_hours,
      };
      const filledKeys = Object.fromEntries(Object.entries(keys).filter(([, v]) => v.trim()));
      if (Object.keys(filledKeys).length) payload.api_keys = filledKeys;
      const updated = await api.updateSettings(payload);
      setS(updated);
      setKeys({});
      onSaved(updated);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1800);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function num(v: string): number {
    const n = Number(v);
    return isNaN(n) ? 0 : n;
  }

  return (
    <div className="settings-page contour-bg">
      <h1 className="detail-h1">Settings</h1>
      <p style={{ color: "var(--ink-soft)", marginTop: 6 }}>
        All settings and API keys are stored locally in the SQLite database. Keys can also be supplied
        via environment variables (<code>SUMMIT_SIGNAL_FIRMS_KEY</code>, <code>SUMMIT_SIGNAL_AIRNOW_KEY</code>, <code>SUMMIT_SIGNAL_NPS_KEY</code>).
      </p>
      {error && <div className="error-note">{error}</div>}

      <div className="settings-grid" style={{ marginTop: 14 }}>
        <div className="settings-card">
          <h3>API keys</h3>
          {KEYED.map((k) => (
            <div className="field" key={k.id}>
              <label>
                {k.label}{" "}
                <span className={`key-present ${s.api_keys_present[k.id] ? "yes" : "no"}`}>
                  {s.api_keys_present[k.id] ? "● key configured" : "○ no key — connector will be skipped"}
                </span>
              </label>
              <input
                type="password"
                placeholder={s.api_keys_present[k.id] ? "•••••• (enter new value to replace)" : "paste key"}
                value={keys[k.id] || ""}
                onChange={(e) => setKeys({ ...keys, [k.id]: e.target.value })}
              />
              <div style={{ fontSize: 11, marginTop: 3 }}>
                <a href={k.url} target="_blank" rel="noreferrer">Get a free key ↗</a>
              </div>
            </div>
          ))}
        </div>

        <div className="settings-card">
          <h3>Connectors</h3>
          <div className="layer-toggles">
            {Object.keys(CONNECTOR_LABELS).map((c) => (
              <label key={c}>
                <input
                  type="checkbox"
                  checked={s.connectors_enabled[c] !== false}
                  onChange={(e) => patch("connectors_enabled", { ...s.connectors_enabled, [c]: e.target.checked })}
                />
                {CONNECTOR_LABELS[c]}
              </label>
            ))}
          </div>
        </div>

        <div className="settings-card">
          <h3>Thresholds</h3>
          <div className="field-row">
            <div className="field">
              <label>Fire search radius (mi)</label>
              <input type="number" value={s.fire_radius_miles} onChange={(e) => patch("fire_radius_miles", num(e.target.value))} />
            </div>
            <div className="field">
              <label>Stale data after (hours)</label>
              <input type="number" value={s.stale_hours} onChange={(e) => patch("stale_hours", num(e.target.value))} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>AQI moderate ≥</label>
              <input type="number" value={s.aqi_moderate_threshold} onChange={(e) => patch("aqi_moderate_threshold", num(e.target.value))} />
            </div>
            <div className="field">
              <label>AQI major ≥</label>
              <input type="number" value={s.aqi_major_threshold} onChange={(e) => patch("aqi_major_threshold", num(e.target.value))} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Gust moderate ≥ (mph)</label>
              <input type="number" value={s.wind_gust_moderate_mph} onChange={(e) => patch("wind_gust_moderate_mph", num(e.target.value))} />
            </div>
            <div className="field">
              <label>Gust major ≥ (mph)</label>
              <input type="number" value={s.wind_gust_major_mph} onChange={(e) => patch("wind_gust_major_mph", num(e.target.value))} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Precip prob moderate ≥ (%)</label>
              <input type="number" value={s.precip_prob_moderate} onChange={(e) => patch("precip_prob_moderate", num(e.target.value))} />
            </div>
            <div className="field">
              <label>Very cold low ≤ (°F)</label>
              <input type="number" value={s.cold_low_f} onChange={(e) => patch("cold_low_f", num(e.target.value))} />
            </div>
          </div>
        </div>

        <div className="settings-card">
          <h3>Local LLM (Ollama) & schedule</h3>
          <div className="layer-toggles" style={{ marginBottom: 8 }}>
            <label>
              <input type="checkbox" checked={s.ollama_enabled} onChange={(e) => patch("ollama_enabled", e.target.checked)} />
              Use local Ollama model for AI summaries (falls back to rule-based)
            </label>
          </div>
          {s.ollama_enabled && (
            <>
              <div className="field">
                <label>Ollama URL</label>
                <input value={s.ollama_url} onChange={(e) => patch("ollama_url", e.target.value)} />
              </div>
              <div className="field">
                <label>
                  Model{" "}
                  {ollamaAvailable === false && <span className="key-present no">○ Ollama not reachable</span>}
                  {ollamaAvailable === true && <span className="key-present yes">● connected</span>}
                </label>
                {ollamaModels.length > 0 ? (
                  <select value={s.ollama_model} onChange={(e) => patch("ollama_model", e.target.value)}>
                    {!ollamaModels.includes(s.ollama_model) && <option value={s.ollama_model}>{s.ollama_model}</option>}
                    {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input value={s.ollama_model} onChange={(e) => patch("ollama_model", e.target.value)} placeholder="llama3.1:8b" />
                )}
              </div>
            </>
          )}
          <div className="field">
            <label>Background re-check every N hours (0 = off)</label>
            <input type="number" value={s.schedule_hours} onChange={(e) => patch("schedule_hours", num(e.target.value))} />
          </div>
        </div>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center" }}>
        <button className="btn primary" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save settings"}
        </button>
        {savedFlash && <span className="key-present yes">● saved</span>}
      </div>
    </div>
  );
}
