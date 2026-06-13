import type { Trip } from "../types";
import { ageLabel } from "../lib/api";
import { TRIP_TYPE_LABELS } from "../types";

interface Props {
  trips: Trip[];
  selectedTripId: number | null;
  onSelect: (trip: Trip) => void;
  onOpenDetail: (trip: Trip) => void;
  onRunAll: () => void;
  runningAll: boolean;
}

function statusDot(status: string | null): string {
  switch (status) {
    case "Major concerns found": return "var(--accent)";
    case "Some concerns found": return "var(--amber)";
    case "No major concerns found": return "var(--teal)";
    case "Source check failed": return "var(--red)";
    case "Data incomplete": return "var(--gray)";
    default: return "var(--line-strong)";
  }
}

export default function SavedTrips({ trips, selectedTripId, onSelect, onOpenDetail, onRunAll, runningAll }: Props) {
  if (trips.length === 0) {
    return <div className="empty-note">No saved trips yet. Search a place, click the map, and save your first trip.</div>;
  }
  return (
    <div>
      {trips.map((t) => (
        <div
          key={t.id}
          className={`trip-item${t.id === selectedTripId ? " selected" : ""}`}
          onClick={() => onSelect(t)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: statusDot(t.latest_concern_status), flexShrink: 0 }} title={t.latest_concern_status || "not yet checked"} />
            <span className="t-name">{t.name}</span>
            {(() => {
              const iso = t.last_checked_at;
              const stale = !iso || (Date.now() - new Date(iso).getTime()) / 3600000 > 12;
              return stale ? <span title="No recent check (>12h)" style={{ color: "#b3261e", marginLeft: 6 }}>●</span> : null;
            })()}
          </div>
          <div className="t-meta">
            {t.start_date} → {t.end_date} · {TRIP_TYPE_LABELS[t.trip_type]}
          </div>
          <div className="t-meta">
            {t.latest_concern_status
              ? `${t.latest_concern_status} · checked ${ageLabel(t.last_checked_at)}`
              : "not yet checked"}
          </div>
          <button
            className="btn ghost small"
            style={{ marginTop: 6 }}
            onClick={(e) => { e.stopPropagation(); onOpenDetail(t); }}
          >
            Detail / history →
          </button>
        </div>
      ))}
      <button className="btn ghost small full" style={{ marginTop: 4 }} disabled={runningAll} onClick={onRunAll}>
        {runningAll ? "Starting checks…" : "Re-check all saved trips"}
      </button>
    </div>
  );
}
