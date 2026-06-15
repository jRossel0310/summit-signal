import type { Trip } from "../types";
import TripForm from "./TripForm";
import SavedTrips from "./SavedTrips";

interface Props {
  loggedIn: boolean;
  selectedPoint: { lat: number; lon: number } | null;
  pointName: string | null;
  trips: Trip[];
  selectedTripId: number | null;
  runningAll: boolean;
  onTripCreated: (trip: Trip) => void;
  onSelectTrip: (trip: Trip) => void;
  onOpenDetail: (trip: Trip) => void;
  onRunAll: () => void;
  onLoginClick: () => void;
}

export default function PlanPanel({
  loggedIn, selectedPoint, pointName, trips, selectedTripId, runningAll,
  onTripCreated, onSelectTrip, onOpenDetail, onRunAll, onLoginClick,
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
    </>
  );
}
