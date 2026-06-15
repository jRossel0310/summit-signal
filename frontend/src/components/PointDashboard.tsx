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

function SectionCard({ s }: { s: PointSection }) {
  return (
    <div className={`point-section point-${s.status}`}>
      <div className="point-section-head">
        <span className="point-section-title">{s.title}</span>
        <span className="point-section-status">{STATUS_LABEL[s.status] ?? s.status}</span>
      </div>
      {s.layer_id === "elevation" && s.status === "ok" ? <ElevationValue data={s.data} /> : null}
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
        (result?.sections || []).map((s) => <SectionCard key={s.layer_id} s={s} />)
      )}
    </div>
  );
}
