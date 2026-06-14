import type { Trip } from "../types";
import type { LayerState } from "./MapView";
import TripForm from "./TripForm";
import SavedTrips from "./SavedTrips";

interface Props {
  loggedIn: boolean;
  selectedPoint: { lat: number; lon: number } | null;
  pointName: string | null;
  trips: Trip[];
  selectedTripId: number | null;
  layers: LayerState;
  runningAll: boolean;
  onTripCreated: (trip: Trip) => void;
  onSelectTrip: (trip: Trip) => void;
  onOpenDetail: (trip: Trip) => void;
  onRunAll: () => void;
  onLayersChange: (layers: LayerState) => void;
  onLoginClick: () => void;
}

const LAYER_ROWS: [keyof LayerState, string][] = [
  ["selectedPoint", "Selected trip point"],
  ["gpxRoute", "GPX route"],
  ["fires", "Active fire detections"],
  ["perimeters", "Fire perimeters"],
  ["savedTrips", "Saved trip markers"],
];

export default function PlanPanel({
  loggedIn, selectedPoint, pointName, trips, selectedTripId, layers, runningAll,
  onTripCreated, onSelectTrip, onOpenDetail, onRunAll, onLayersChange, onLoginClick,
}: Props) {
  return (
    <>
      {loggedIn ? (
        <>
          <div className="section">
            <h2 className="section-title">New trip</h2>
            <TripForm selectedPoint={selectedPoint} locationName={pointName} onCreated={onTripCreated} />
          </div>
          <div className="section">
            <h2 className="section-title">Saved trips ({trips.length})</h2>
            <SavedTrips
              trips={trips}
              selectedTripId={selectedTripId}
              onSelect={onSelectTrip}
              onOpenDetail={onOpenDetail}
              onRunAll={onRunAll}
              runningAll={runningAll}
            />
          </div>
        </>
      ) : (
        <div className="section">
          <div className="empty-note">
            Log in to save trips and run condition checks. You can browse and search the map without an account.
          </div>
          <button className="btn primary" style={{ marginTop: 8 }} onClick={onLoginClick}>Log in / Sign up</button>
        </div>
      )}

      <div className="section">
        <h2 className="section-title">Map layers</h2>
        <div className="layer-toggles">
          <label>
            <input
              type="checkbox"
              checked={layers.basemap === "topo"}
              onChange={(e) => onLayersChange({ ...layers, basemap: e.target.checked ? "topo" : "street" })}
            />
            Topo basemap (off = street)
          </label>
          {LAYER_ROWS.map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={layers[key] as boolean}
                onChange={(e) => onLayersChange({ ...layers, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="layer-note">
          Fire detections and perimeters appear after a condition check returns data for the selected trip.
          AQI, NWS alert areas, and avalanche regions are shown in the conditions panel with source links.
        </div>
      </div>
    </>
  );
}
