import { useEffect, useState } from "react";
import type { AppSettings, SettingsUpdate } from "../types";
import { CONNECTOR_LABELS } from "../types";
import { api } from "../lib/api";

interface Props {
  onSaved: (s: AppSettings) => void;
}

export default function SettingsView({ onSaved }: Props) {
  const [s, setS] = useState<AppSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setS).catch((e) => setError((e as Error).message));
  }, []);

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
      };
      const updated = await api.updateSettings(payload);
      setS(updated);
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
        Your settings are saved to your account. Source API keys are configured by the operator.
      </p>
      {error && <div className="error-note">{error}</div>}

      <div className="settings-grid" style={{ marginTop: 14 }}>
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
