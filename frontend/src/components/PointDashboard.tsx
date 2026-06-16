import type { SelectionResult, PointSection } from "../layers/types";

interface Props {
  coords: { lat: number; lon: number } | null;
  result: SelectionResult | null;
  loading: boolean;
  error: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "ok",
  loading: "loading…",
  empty: "no data",
  error: "error",
  "needs-key": "needs key",
  "coming-soon": "coming soon",
};

function ElevationValue({ data }: { data: Record<string, unknown> | null | undefined }) {
  const ft = data?.elevation_ft as number | undefined;
  return <div className="point-elev">{ft != null ? `${ft.toLocaleString()} ft` : "—"}</div>;
}

function SlopeAspectValue({ data }: { data: Record<string, unknown> | null | undefined }) {
  const slope = data?.slope_deg as number | undefined;
  const compass = data?.aspect_compass as string | undefined;
  const bucket = data?.slope_bucket as string | undefined;
  if (slope == null) return null;
  return (
    <div className="point-elev">
      {Math.round(slope)}° · {compass ?? "—"}
      {bucket ? <span className="point-bucket"> · {bucket} band</span> : null}
    </div>
  );
}

function fmt(v: unknown, suffix = "") { return v == null ? "—" : `${v}${suffix}`; }

function aspectNote(compass: string): string {
  const c = compass.toUpperCase();
  if (["S", "SE", "SW"].includes(c)) return "sun-exposed, softens early";
  if (["N", "NE", "NW"].includes(c)) return "shaded, stays firm";
  return "partial sun";
}

function HazardValue({ s, aspectCompass }: { s: PointSection; aspectCompass?: string }) {
  const d = (s.data || {}) as Record<string, unknown>;
  switch (s.layer_id) {
    case "current_weather":
      return <div className="point-elev">{fmt(d.temp_f, "°F")} · {fmt(d.conditions)}
        <span className="point-bucket"> · wind {fmt(d.wind_mph)}{d.gust_mph ? `–${d.gust_mph}` : ""} mph · RH {fmt(d.humidity_pct, "%")}</span></div>;
    case "aqi":
      return <div className="point-elev">AQI {fmt(d.max_aqi)}<span className="point-bucket"> · {fmt(d.category)}</span></div>;
    case "wildfire":
      return <div className="point-elev">{fmt(d.count)} fire(s)<span className="point-bucket"> · nearest {fmt(d.nearest_miles)} mi</span></div>;
    case "avalanche":
      return <div className="point-elev">{fmt(d.danger)}<span className="point-bucket"> · {fmt(d.center)}</span></div>;
    case "snow":
      return <div className="point-elev">{fmt(d.snow_depth_in, " in")} deep<span className="point-bucket"> · {fmt(d.recent_snowfall_in, " in")} recent</span></div>;
    case "freeze_thaw":
      return <div className="point-elev">low {fmt(d.overnight_low_f, "°F")} · {fmt(d.hours_below_freezing)} h &lt; 32°
        <span className="point-bucket"> · refreeze {fmt(d.refreeze)} · AM warming {fmt(d.morning_warming_f_per_hr)}°/h{aspectCompass ? ` · ${aspectNote(aspectCompass)}` : ""}</span></div>;
    default:
      return null;
  }
}

const HAZARD_IDS = new Set(["current_weather", "aqi", "wildfire", "avalanche", "snow", "freeze_thaw"]);

function SectionCard({ s, aspectCompass }: { s: PointSection; aspectCompass?: string }) {
  return (
    <div className={`point-section point-${s.status}`}>
      <div className="point-section-head">
        <span className="point-section-title">{s.title}</span>
        <span className="point-section-status">{STATUS_LABEL[s.status] ?? s.status}</span>
      </div>
      {s.layer_id === "elevation" && s.status === "ok" ? <ElevationValue data={s.data} /> : null}
      {s.layer_id === "slope_aspect" && s.status === "ok" ? <SlopeAspectValue data={s.data} /> : null}
      {HAZARD_IDS.has(s.layer_id) && s.status === "ok" ? <HazardValue s={s} aspectCompass={aspectCompass} /> : null}
      {s.message ? <div className="point-section-msg">{s.message}</div> : null}
      {s.source ? (
        <div className="point-section-src">
          {s.source.url ? (
            <a href={s.source.url} target="_blank" rel="noreferrer">{s.source.name}</a>
          ) : (
            s.source.name
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function PointDashboard({ coords, result, loading, error }: Props) {
  if (!coords) {
    return (
      <div className="empty-note">
        Click the map to inspect a point — elevation now, and more as layers ship.
      </div>
    );
  }
  return (
    <div className="point-dashboard">
      <div className="point-head">
        <div className="point-place">{result?.place_name || "Selected point"}</div>
        <div className="point-coords">{coords.lat.toFixed(4)}, {coords.lon.toFixed(4)}</div>
      </div>
      {error ? <div className="point-error">{error}</div> : null}
      {loading && !result ? (
        <div className="point-skeleton">Loading point context…</div>
      ) : (
        (result?.sections || []).map((s) => (
          <SectionCard key={s.layer_id} s={s}
            aspectCompass={(result?.sections.find((x) => x.layer_id === "slope_aspect")?.data?.aspect_compass as string | undefined)} />
        ))
      )}
    </div>
  );
}
