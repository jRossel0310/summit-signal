import { useMemo } from "react";
import type { CheckStatus, ConditionCheckDetail, ConnectorResult, RiskFlag, Trip } from "../types";
import { CONNECTOR_LABELS } from "../types";
import { api, fmtTime } from "../lib/api";
import { ConnStatus, Freshness, SeverityBadge, StatusBanner } from "./Badges";
import Markdown from "./Markdown";

interface Props {
  trip: Trip | null;
  check: ConditionCheckDetail | null;
  liveStatus: CheckStatus | null; // while running
  running: boolean;
  loadingCheck: boolean;
  error: string | null;
  staleHours: number;
  onRunCheck: () => void;
  onRegenerateSummary: () => void;
  regenBusy: boolean;
}

const SEV_ORDER: Record<string, number> = { major: 0, moderate: 1, unknown: 2, info: 3 };

const STALE_HOURS = 12;
function checkAgeHours(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / 3600000;
}

function ConnectorCard({ r, staleHours }: { r: ConnectorResult; staleHours: number }) {
  const n = (r.normalized || {}) as Record<string, any>;
  const label = CONNECTOR_LABELS[r.connector_name] || r.connector_name;

  const body = useMemo(() => {
    switch (r.connector_name) {
      case "nws_weather": {
        if (!n.periods) return null;
        return (
          <div className="kv">
            {n.high_f != null && <><span className="k">High / Low</span><span className="v">{n.high_f}°F / {n.low_f ?? "?"}°F</span></>}
            {n.max_wind_mph != null && <><span className="k">Max wind</span><span className="v">{n.max_wind_mph} mph</span></>}
            {n.max_precip_chance != null && <><span className="k">Max precip</span><span className="v">{n.max_precip_chance}%</span></>}
            <span className="k">Snow / thunder</span>
            <span className="v">{n.snow_mentioned ? "snow mentioned" : "no snow"} · {n.thunder_mentioned ? "thunder mentioned" : "no thunder"}</span>
            {Array.isArray(n.alerts) && n.alerts.length > 0 && (
              <><span className="k">Alerts</span>
                <span className="v">{n.alerts.map((a: any) => a.event).join("; ")}</span></>
            )}
          </div>
        );
      }
      case "usgs_elevation":
        return n.elevation_ft != null ? (
          <div className="kv">
            <span className="k">Elevation</span>
            <span className="v">{Math.round(n.elevation_ft).toLocaleString()} ft{n.elevation_m != null ? ` (${Math.round(n.elevation_m)} m)` : ""}{n.fallback_source ? ` · via ${n.fallback_source}` : ""}</span>
          </div>
        ) : null;
      case "elevation_adjusted": {
        const bands = n.bands as any[] | undefined;
        if (!bands?.length) return null;
        return (
          <>
            <div className="kv">
              {bands.map((b, i) => (
                <Fragmented key={i} k={`${b.label} (${Math.round(b.elevation_ft).toLocaleString()} ft)`} v={`${b.est_high_f != null ? Math.round(b.est_high_f) + "°F" : "?"} / ${b.est_low_f != null ? Math.round(b.est_low_f) + "°F" : "?"}`} />
              ))}
            </div>
            {n.warning && <div style={{ fontSize: 11.5, color: "var(--amber)", marginTop: 5, fontFamily: "var(--mono)" }}>⚠ {n.warning}</div>}
          </>
        );
      }
      case "nasa_firms": {
        if (n.detection_count == null) return null;
        return (
          <div className="kv">
            <span className="k">Detections (3d)</span><span className="v">{n.detection_count}</span>
            {n.nearest_miles != null && <><span className="k">Nearest</span><span className="v">{Number(n.nearest_miles).toFixed(1)} mi</span></>}
          </div>
        );
      }
      case "nifc_wfigs": {
        if (n.perimeter_count == null) return null;
        return (
          <div className="kv">
            <span className="k">Perimeters nearby</span><span className="v">{n.perimeter_count}</span>
            <span className="k">Point inside</span><span className="v">{n.point_inside_perimeter ? "YES" : "no"}</span>
            {n.nearest_miles != null && <><span className="k">Nearest</span><span className="v">{Number(n.nearest_miles).toFixed(1)} mi</span></>}
          </div>
        );
      }
      case "airnow": {
        if (n.max_aqi == null) return null;
        return (
          <>
            <div className="kv">
              <span className="k">Max AQI</span><span className="v">{n.max_aqi} ({n.max_category || "?"})</span>
            </div>
            {n.note && <div style={{ fontSize: 11, color: "var(--ink-soft)", marginTop: 4 }}>{n.note}</div>}
          </>
        );
      }
      case "nps_alerts": {
        if (n.applicable === false) return <div style={{ fontSize: 12.5 }}>Not applicable - no NPS unit near this point.</div>;
        const alerts = n.alerts as any[] | undefined;
        return (
          <div className="kv">
            <span className="k">Units checked</span>
            <span className="v">{(n.parks as any[] | undefined)?.map((p) => p.name).join(", ") || "-"}</span>
            <span className="k">Alerts</span><span className="v">{alerts?.length ?? 0}</span>
          </div>
        );
      }
      case "avalanche": {
        return (
          <>
            <div className="kv">
              <span className="k">Forecast region</span>
              <span className="v">{n.zone_name || n.center_name || "none identified"}</span>
              {n.danger && <><span className="k">Danger (listed)</span><span className="v">{n.danger}</span></>}
            </div>
            {n.forecast_link && (
              <div style={{ marginTop: 5, fontSize: 12 }}>
                <a href={n.forecast_link} target="_blank" rel="noreferrer">Open avalanche forecast →</a>
              </div>
            )}
            {n.manual_check_required && (
              <div style={{ fontSize: 11.5, color: "var(--accent)", marginTop: 5, fontFamily: "var(--mono)", fontWeight: 600 }}>
                ⚠ MANUAL AVALANCHE FORECAST CHECK REQUIRED
              </div>
            )}
          </>
        );
      }
      case "weather_discussion": {
        const hl = n.highlights as Record<string, string[]> | undefined;
        const topics = hl ? Object.keys(hl).filter((t) => hl[t]?.length) : [];
        if (!topics.length) return n.office ? <div style={{ fontSize: 12.5 }}>AFD retrieved for {n.office}; no flagged keywords.</div> : null;
        return (
          <div className="kv">
            {topics.map((t) => (
              <Fragmented key={t} k={t.replace("_", " ")} v={(hl![t][0] || "").slice(0, 140) + (hl![t][0]?.length > 140 ? "…" : "")} />
            ))}
          </div>
        );
      }
      default:
        return null;
    }
  }, [r]);

  return (
    <div className="conn-row">
      <div className="head">
        <span className="name">{label}</span>
        <span style={{ marginLeft: "auto" }}><ConnStatus status={r.status} /></span>
      </div>
      <div className="meta">
        <span>source: {r.source_name || "-"}</span>
        <Freshness retrievedAt={r.retrieved_at} staleHours={staleHours} />
        {r.source_timestamp && <span title="timestamp reported by the source">source ts: {fmtTime(r.source_timestamp)}</span>}
        {r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">source link ↗</a>}
      </div>
      {body && <div className="body">{body}</div>}
      {r.error_message && <div className="err">{r.error_message}</div>}
    </div>
  );
}

function Fragmented({ k, v }: { k: string; v: string }) {
  return (<><span className="k">{k}</span><span className="v">{v}</span></>);
}

export default function ConditionDashboard({
  trip, check, liveStatus, running, loadingCheck, error, staleHours,
  onRunCheck, onRegenerateSummary, regenBusy,
}: Props) {
  if (!trip) {
    return (
      <div className="section">
        <h2 className="section-title">Condition dashboard</h2>
        <div className="empty-note">
          Select a saved trip or create a new one, then run a condition check. Results from each
          source appear here with timestamps, links, concern flags, and an AI planning summary.
        </div>
      </div>
    );
  }

  const flags = (check?.risk_flags || []).slice().sort(
    (a: RiskFlag, b: RiskFlag) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  );

  return (
    <div>
      <div className="section">
        <h2 className="section-title">Condition dashboard - {trip.name}</h2>

        <StatusBanner
          status={running ? "Check in progress…" : check?.overall_concern_status || trip.latest_concern_status}
          sub={
            check?.data_completeness_score != null
              ? `data completeness ${(check.data_completeness_score * 100).toFixed(0)}% · checked ${fmtTime(check.completed_at)}`
              : undefined
          }
        />

        {running && liveStatus && (
          <div className="progress-wrap">
            <div className="progress-bar">
              <div
                className="fill"
                style={{ width: `${(liveStatus.connectors_completed / Math.max(liveStatus.connectors_total, 1)) * 100}%` }}
              />
            </div>
            <div className="progress-label">
              {liveStatus.connectors_completed}/{liveStatus.connectors_total} connectors
              {liveStatus.current_connector ? ` · running: ${CONNECTOR_LABELS[liveStatus.current_connector] || liveStatus.current_connector}` : ""}
            </div>
          </div>
        )}

        {error && <div className="error-note">{error}</div>}

        {(() => {
          const age = checkAgeHours(trip.last_checked_at);
          if (age === null) return (
            <div className="error-note" style={{ background: "#f3efe7", color: "#5f5320", borderColor: "#d8cda8" }}>
              No condition check yet. Run one for current conditions.
            </div>
          );
          if (age > STALE_HOURS) return (
            <div className="error-note" style={{ background: "#f3efe7", color: "#5f5320", borderColor: "#d8cda8" }}>
              Conditions last checked {Math.round(age)}h ago. Re-run for current data.
            </div>
          );
          return null;
        })()}

        <div className="dash-actions">
          <button className="btn primary" disabled={running} onClick={onRunCheck}>
            {running ? "Running…" : "Run condition check"}
          </button>
          {check && check.status === "complete" && (
            <button className="btn ghost" onClick={async () => {
              try {
                const html = await api.fetchReportHtml(trip.id, check.id);
                const blob = new Blob([html], { type: "text/html" });
                const url = URL.createObjectURL(blob);
                window.open(url, "_blank");
                setTimeout(() => URL.revokeObjectURL(url), 60000);
              } catch { /* ignore report open failure */ }
            }}>
              Print report
            </button>
          )}
        </div>
      </div>

      {loadingCheck && <div className="section"><div className="empty-note">Loading latest check…</div></div>}

      {check && (
        <>
          <div className="section">
            <h2 className="section-title">Concern flags ({flags.length})</h2>
            {flags.length === 0 && <div className="empty-note">No flags recorded for this check.</div>}
            {flags.map((f) => (
              <div className="flag-row" key={f.id}>
                <SeverityBadge severity={f.severity} />
                <div className="f-body">
                  <div className="f-title">{f.title}</div>
                  {f.description && <div className="f-desc">{f.description}</div>}
                  <div className="f-src">
                    {f.category}{f.source_connector ? ` · ${CONNECTOR_LABELS[f.source_connector] || f.source_connector}` : ""}
                    {f.confidence ? ` · confidence: ${f.confidence}` : ""}
                    {f.source_url && <> · <a href={f.source_url} target="_blank" rel="noreferrer">source ↗</a></>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="section">
            <h2 className="section-title">AI planning summary</h2>
            {check.ai_summary ? (
              <>
                <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-soft)", marginBottom: 6 }}>
                  generator: {check.ai_summary.generator}
                </div>
                <Markdown text={check.ai_summary.summary_text} />
                <button className="btn ghost small" style={{ marginTop: 8 }} disabled={regenBusy} onClick={onRegenerateSummary}>
                  {regenBusy ? "Regenerating…" : "Regenerate summary"}
                </button>
              </>
            ) : (
              <div className="empty-note">No summary generated yet.</div>
            )}
          </div>

          <div className="section">
            <h2 className="section-title">Source results ({check.connector_results.length})</h2>
            {check.connector_results.map((r) => (
              <ConnectorCard key={r.id} r={r} staleHours={staleHours} />
            ))}
          </div>
        </>
      )}

      {!check && !running && !loadingCheck && (
        <div className="section">
          <div className="empty-note">No condition check yet for this trip. Run one to pull live data from NWS, USGS, FIRMS, WFIGS, AirNow, NPS, and avalanche.org.</div>
        </div>
      )}
    </div>
  );
}
