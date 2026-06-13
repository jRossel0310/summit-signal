import { useEffect, useState } from "react";
import type { ConditionCheck, ConditionCheckDetail, Trip } from "../types";
import { TRIP_TYPE_LABELS } from "../types";
import { api, fmtTime } from "../lib/api";
import { SeverityBadge, StatusBanner, statusBannerClass } from "./Badges";
import Markdown from "./Markdown";

interface Props {
  trip: Trip;
  staleHours: number;
  onBack: () => void;
  onTripUpdated: (t: Trip) => void;
  onTripDeleted: (id: number) => void;
}

export default function TripDetail({ trip, onBack, onTripUpdated, onTripDeleted }: Props) {
  const [checks, setChecks] = useState<ConditionCheck[]>([]);
  const [activeCheck, setActiveCheck] = useState<ConditionCheckDetail | null>(null);
  const [notes, setNotes] = useState(trip.notes || "");
  const [savingNotes, setSavingNotes] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.listChecks(trip.id)
      .then(async (list) => {
        if (cancelled) return;
        setChecks(list);
        const latest = list.find((c) => c.status === "complete");
        if (latest) {
          const detail = await api.getCheck(latest.id);
          if (!cancelled) setActiveCheck(detail);
        }
      })
      .catch((e) => !cancelled && setError((e as Error).message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [trip.id]);

  async function openCheck(id: number) {
    setError(null);
    try {
      setActiveCheck(await api.getCheck(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveNotes() {
    setSavingNotes(true);
    try {
      const updated = await api.updateTrip(trip.id, { notes });
      onTripUpdated(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingNotes(false);
    }
  }

  async function deleteTrip() {
    if (!confirm(`Delete trip "${trip.name}" and all of its checks?`)) return;
    try {
      await api.deleteTrip(trip.id);
      onTripDeleted(trip.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="detail-page">
      <div className="detail-main contour-bg">
        <button className="btn ghost small" onClick={onBack}>← Back to map</button>
        <h1 className="detail-h1" style={{ marginTop: 12 }}>{trip.name}</h1>
        <div className="detail-meta">
          <span>{trip.location_name || "unnamed location"}</span>
          <span>{trip.latitude.toFixed(5)}, {trip.longitude.toFixed(5)}</span>
          <span>{trip.start_date} → {trip.end_date}</span>
          <span>{TRIP_TYPE_LABELS[trip.trip_type]}</span>
          {trip.gpx_route && (
            <span>
              GPX: {trip.gpx_route.length_miles != null ? `${trip.gpx_route.length_miles.toFixed(1)} mi` : "—"}
              {trip.gpx_route.min_elevation_ft != null && trip.gpx_route.max_elevation_ft != null &&
                `, ${Math.round(trip.gpx_route.min_elevation_ft).toLocaleString()}–${Math.round(trip.gpx_route.max_elevation_ft).toLocaleString()} ft`}
            </span>
          )}
        </div>

        <StatusBanner status={activeCheck?.overall_concern_status || trip.latest_concern_status} />

        {error && <div className="error-note">{error}</div>}
        {loading && <div className="empty-note">Loading checks…</div>}

        {activeCheck?.ai_summary && (
          <div className="card" style={{ marginTop: 10 }}>
            <div className="card-head">
              <span className="card-title">Planning summary</span>
              <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-soft)" }}>
                {fmtTime(activeCheck.completed_at)} · {activeCheck.ai_summary.generator}
              </span>
            </div>
            <Markdown text={activeCheck.ai_summary.summary_text} />
          </div>
        )}

        {activeCheck && activeCheck.risk_flags.length > 0 && (
          <div className="card">
            <div className="card-head"><span className="card-title">Flags for this check</span></div>
            {activeCheck.risk_flags.map((f) => (
              <div className="flag-row" key={f.id}>
                <SeverityBadge severity={f.severity} />
                <div className="f-body">
                  <div className="f-title">{f.title}</div>
                  {f.description && <div className="f-desc">{f.description}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="detail-side">
        <div className="section" style={{ paddingTop: 4 }}>
          <h2 className="section-title">Actions</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {activeCheck && (
              <button className="btn full" onClick={async () => {
                try {
                  const html = await api.fetchReportHtml(trip.id, activeCheck.id);
                  const blob = new Blob([html], { type: "text/html" });
                  const url = URL.createObjectURL(blob);
                  window.open(url, "_blank");
                  setTimeout(() => URL.revokeObjectURL(url), 60000);
                } catch (e) { setError((e as Error).message); }
              }}>
                Print / export report
              </button>
            )}
            <button className="btn ghost full" onClick={deleteTrip} style={{ color: "var(--red)", borderColor: "var(--red)" }}>
              Delete trip
            </button>
          </div>
        </div>

        <div className="section">
          <h2 className="section-title">Check history ({checks.length})</h2>
          {checks.length === 0 && <div className="empty-note">No condition checks yet.</div>}
          {checks.map((c) => (
            <div key={c.id} className="history-row" onClick={() => c.status === "complete" && openCheck(c.id)}>
              <span className="h-time">{fmtTime(c.started_at)}</span>
              <span className={`badge ${c.status === "failed" ? "major" : statusBannerClass(c.overall_concern_status) === "s-major" ? "major" : statusBannerClass(c.overall_concern_status) === "s-some" ? "moderate" : statusBannerClass(c.overall_concern_status) === "s-none" ? "info" : "unknown"}`}>
                {c.status === "running" ? "running" : c.overall_concern_status || c.status}
              </span>
              {activeCheck?.id === c.id && <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 10 }}>viewing</span>}
            </div>
          ))}
        </div>

        <div className="section">
          <h2 className="section-title">Manual notes</h2>
          <textarea rows={6} style={{ width: "100%", padding: 8, border: "1px solid var(--line-strong)", borderRadius: 3 }} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <button className="btn small" style={{ marginTop: 6 }} disabled={savingNotes} onClick={saveNotes}>
            {savingNotes ? "Saving…" : "Save notes"}
          </button>
        </div>
      </div>
    </div>
  );
}
