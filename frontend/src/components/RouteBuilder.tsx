import type { RouteBuilderState } from "../hooks/useRouteBuilder";
import type { Trip } from "../types";

interface Props {
  rb: RouteBuilderState;
  loggedIn: boolean;
  selectedTripId: number | null;
  selectedTripName: string | null;
  onSaved: (trip: Trip) => void;
}

const R = 3958.8;
function haversineMiles(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const p1 = (a.lat * Math.PI) / 180;
  const p2 = (b.lat * Math.PI) / 180;
  const dp = ((b.lat - a.lat) * Math.PI) / 180;
  const dl = ((b.lon - a.lon) * Math.PI) / 180;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function manualMiles(waypoints: { lat: number; lon: number }[]): number {
  let total = 0;
  for (let i = 1; i < waypoints.length; i++) total += haversineMiles(waypoints[i - 1], waypoints[i]);
  return total;
}

export default function RouteBuilder({
  rb, loggedIn, selectedTripId, selectedTripName, onSaved,
}: Props) {
  if (!loggedIn) return null;

  const isSnapped = !!rb.snappedPoints && !!rb.snapped;
  const miles = isSnapped && rb.snapped!.length_miles != null
    ? rb.snapped!.length_miles
    : manualMiles(rb.waypoints);
  const provider = isSnapped ? rb.snapped!.provider : "manual";
  const profile = isSnapped ? rb.snapped!.profile : "-";

  async function handleSave() {
    if (selectedTripId == null) return;
    const trip = await rb.save(selectedTripId);
    if (trip) onSaved(trip);
  }

  return (
    <div className="route-builder-panel">
      <button className="btn small full" onClick={rb.toggleMode}>
        {rb.mode ? "✕ Exit route builder" : "✎ Build route"}
      </button>

      {rb.mode && (
        <div className="route-builder-body">
          <div className="rb-hint">Click the map to add waypoints. Drag a marker to adjust.</div>

          <div className="rb-stats">
            <div><span className="rb-k">Distance</span><span className="rb-v">{miles.toFixed(2)} mi</span></div>
            <div><span className="rb-k">Waypoints</span><span className="rb-v">{rb.waypoints.length}</span></div>
            <div><span className="rb-k">Mode</span><span className="rb-v">{isSnapped ? "snapped" : "manual"}</span></div>
            <div><span className="rb-k">Provider</span><span className="rb-v">{provider}{isSnapped ? ` · ${profile}` : ""}</span></div>
          </div>

          {rb.snapped && rb.stale && (
            <div className="rb-warn">Snapped route is stale — re-snap to update it.</div>
          )}
          {rb.message && <div className="rb-warn">{rb.message}</div>}

          <div className="rb-actions">
            <button className="btn small" disabled={rb.busy || rb.waypoints.length === 0} onClick={rb.undoLast}>Undo last</button>
            <button className="btn small" disabled={rb.busy || rb.waypoints.length === 0} onClick={rb.clear}>Clear</button>
            <button className="btn small" disabled={rb.busy || rb.waypoints.length < 2} onClick={rb.snap}>
              {rb.busy ? "Snapping…" : "Snap to trails"}
            </button>
          </div>

          <button
            className="btn primary small full"
            disabled={rb.busy || rb.waypoints.length < 2 || selectedTripId == null}
            onClick={handleSave}
          >
            {selectedTripId == null
              ? "Select a trip to save"
              : `Save ${isSnapped ? "snapped" : "manual"} route to ${selectedTripName || "trip"}`}
          </button>

          <div className="rb-disclaimer">
            Trail snapping uses available routing/map data and may be incomplete or wrong.
            Verify official maps, access restrictions, permits, seasonal closures, and current
            conditions before relying on this route.
          </div>
        </div>
      )}
    </div>
  );
}
