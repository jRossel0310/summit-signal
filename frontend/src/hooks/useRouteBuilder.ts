import { useCallback, useMemo, useState } from "react";
import { api } from "../lib/api";
import type {
  BuiltRouteSaveRequest, RouteSnapResponse, RouteWaypoint, Trip,
} from "../types";

export interface RouteBuilderState {
  mode: boolean;
  waypoints: RouteWaypoint[];
  snapped: RouteSnapResponse | null;
  stale: boolean;            // waypoints edited since the last successful snap
  busy: boolean;
  message: string | null;
  manualPoints: [number, number, number | null][];
  snappedPoints: [number, number, number | null][] | null;
  toggleMode: () => void;
  addWaypoint: (lat: number, lon: number) => void;
  moveWaypoint: (index: number, lat: number, lon: number) => void;
  undoLast: () => void;
  clear: () => void;
  snap: () => Promise<void>;
  save: (tripId: number) => Promise<Trip | null>;
}

export function useRouteBuilder(): RouteBuilderState {
  const [mode, setMode] = useState(false);
  const [waypoints, setWaypoints] = useState<RouteWaypoint[]>([]);
  const [snapped, setSnapped] = useState<RouteSnapResponse | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const manualPoints = useMemo<[number, number, number | null][]>(
    () => waypoints.map((w) => [w.lat, w.lon, null]),
    [waypoints],
  );
  const snappedPoints = useMemo(
    () => (snapped && snapped.status === "success" && !stale ? snapped.points : null),
    [snapped, stale],
  );

  const toggleMode = useCallback(() => setMode((m) => !m), []);

  const addWaypoint = useCallback((lat: number, lon: number) => {
    setWaypoints((w) => [...w, { lat, lon }]);
    setStale(true);
  }, []);

  const moveWaypoint = useCallback((index: number, lat: number, lon: number) => {
    setWaypoints((w) => w.map((p, i) => (i === index ? { lat, lon } : p)));
    setStale(true);
  }, []);

  const undoLast = useCallback(() => {
    setWaypoints((w) => w.slice(0, -1));
    setStale(true);
  }, []);

  const clear = useCallback(() => {
    setWaypoints([]);
    setSnapped(null);
    setStale(false);
    setMessage(null);
  }, []);

  const snap = useCallback(async () => {
    if (waypoints.length < 2) {
      setMessage("Add at least two waypoints to snap.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.snapRoute({
        waypoints,
        profile: "hiking",
        options: { preferTrails: true, avoidRoads: true },
      });
      setSnapped(res);
      setStale(false);
      if (res.status === "unavailable") {
        setMessage(
          "Trail snapping unavailable (no routing provider configured). " +
          "You can still save this as a manual, unsnapped route.",
        );
      } else if (res.status === "failed") {
        setMessage(
          (res.message || "Trail snapping failed.") +
          " You can still save this as a manual route.",
        );
      } else {
        setMessage(null);
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [waypoints]);

  const save = useCallback(async (tripId: number): Promise<Trip | null> => {
    if (waypoints.length < 2) {
      setMessage("Add at least two waypoints first.");
      return null;
    }
    const useSnapped = !!snappedPoints && !!snapped;
    const req: BuiltRouteSaveRequest = useSnapped
      ? {
          name: "Snapped route",
          points: snapped!.points,
          bbox: snapped!.bbox,
          length_miles: snapped!.length_miles,
          source: "openrouteservice",
          profile: snapped!.profile,
          metadata: snapped!.metadata,
        }
      : {
          name: "Manual route",
          points: manualPoints,
          bbox: null,
          length_miles: null,
          source: "manual",
          profile: null,
          metadata: {},
        };
    setBusy(true);
    setMessage(null);
    try {
      const trip = await api.saveBuiltRoute(tripId, req);
      clear();
      setMode(false);
      return trip;
    } catch (e) {
      setMessage((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }, [waypoints, snapped, snappedPoints, manualPoints, clear]);

  return {
    mode, waypoints, snapped, stale, busy, message,
    manualPoints, snappedPoints,
    toggleMode, addWaypoint, moveWaypoint, undoLast, clear, snap, save,
  };
}
