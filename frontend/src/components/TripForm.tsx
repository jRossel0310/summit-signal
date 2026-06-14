import { useState } from "react";
import { api } from "../lib/api";
import type { Trip, TripCreate, TripType } from "../types";
import { TRIP_TYPE_LABELS } from "../types";

interface Props {
  selectedPoint: { lat: number; lon: number } | null;
  locationName: string | null;
  onCreated: (trip: Trip) => void;
}

function plusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function TripForm({ selectedPoint, locationName, onCreated }: Props) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState(plusDays(7));
  const [endDate, setEndDate] = useState(plusDays(9));
  const [tripType, setTripType] = useState<TripType>("general");
  const [notes, setNotes] = useState("");
  const [trailheadFt, setTrailheadFt] = useState("");
  const [midFt, setMidFt] = useState("");
  const [highFt, setHighFt] = useState("");
  const [gpxFile, setGpxFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!selectedPoint) { setError("Select a point on the map first (click the map or search)."); return; }
    if (!name.trim()) { setError("Trip name is required."); return; }
    if (endDate < startDate) { setError("End date must be on or after start date."); return; }
    setSaving(true);
    setError(null);
    try {
      const bands =
        trailheadFt || midFt || highFt
          ? {
              trailhead_ft: trailheadFt ? Number(trailheadFt) : null,
              mid_ft: midFt ? Number(midFt) : null,
              high_ft: highFt ? Number(highFt) : null,
            }
          : null;
      const payload: TripCreate = {
        name: name.trim(),
        location_name: locationName,
        latitude: selectedPoint.lat,
        longitude: selectedPoint.lon,
        start_date: startDate,
        end_date: endDate,
        trip_type: tripType,
        notes: notes.trim() || null,
        elevation_bands: bands,
      };
      let trip = await api.createTrip(payload);
      if (gpxFile) {
        try {
          trip = await api.uploadGpx(trip.id, gpxFile);
        } catch (e) {
          setError(`Trip saved, but GPX upload failed: ${(e as Error).message}`);
        }
      }
      onCreated(trip);
      setName(""); setNotes(""); setGpxFile(null);
      setTrailheadFt(""); setMidFt(""); setHighFt("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="field">
        <label>Trip name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Enchantments thru-hike" />
      </div>
      <div className="field">
        <label>Location point</label>
        <input
          readOnly
          value={
            selectedPoint
              ? `${selectedPoint.lat.toFixed(5)}, ${selectedPoint.lon.toFixed(5)}${locationName ? ` - ${locationName}` : ""}`
              : "click the map or use search"
          }
          style={{ background: "var(--panel-2)", fontFamily: "var(--mono)", fontSize: 11.5 }}
        />
      </div>
      <div className="field-row">
        <div className="field">
          <label>Start date</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="field">
          <label>End date</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>Trip type</label>
        <select value={tripType} onChange={(e) => setTripType(e.target.value as TripType)}>
          {(Object.keys(TRIP_TYPE_LABELS) as TripType[]).map((t) => (
            <option key={t} value={t}>{TRIP_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Elevation bands (optional, ft)</label>
        <div className="field-row elevation">
          <input placeholder="Trailhead" inputMode="numeric" value={trailheadFt} onChange={(e) => setTrailheadFt(e.target.value.replace(/[^\d]/g, ""))} />
          <input placeholder="Mid-route" inputMode="numeric" value={midFt} onChange={(e) => setMidFt(e.target.value.replace(/[^\d]/g, ""))} />
          <input placeholder="High point" inputMode="numeric" value={highFt} onChange={(e) => setHighFt(e.target.value.replace(/[^\d]/g, ""))} />
        </div>
      </div>
      <div className="field">
        <label>Notes (optional)</label>
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Permits, partners, bail options…" />
      </div>
      <div className="field">
        <label>GPX route (optional)</label>
        <input
          type="file"
          accept=".gpx,application/gpx+xml"
          onChange={(e) => setGpxFile(e.target.files?.[0] || null)}
        />
      </div>
      {error && <div className="error-note">{error}</div>}
      <button className="btn primary full" disabled={saving} onClick={save}>
        {saving ? "Saving…" : "Save trip"}
      </button>
    </div>
  );
}
