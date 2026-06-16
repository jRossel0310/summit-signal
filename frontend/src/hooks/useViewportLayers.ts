import { useEffect, useRef } from "react";
import type maplibregl from "maplibre-gl";
import type { LayerStateMap } from "../layers/types";
import { api } from "../lib/api";

// registry id -> maplibre geojson source id (set up in MapView)
const VIEWPORT_SOURCES: Record<string, { source: string; layer: string }> = {
  "overlay.fires": { source: "fires", layer: "fires-circle" },
  "overlay.perimeters": { source: "perims", layer: "perims-fill" },
  "overlay.aqi": { source: "aqi", layer: "aqi-circle" },
  "overlay.avalanche": { source: "avy", layer: "avy-fill" },
};
const LAYER_API_ID: Record<string, string> = {
  "overlay.fires": "fires", "overlay.perimeters": "perimeters",
  "overlay.aqi": "aqi", "overlay.avalanche": "avalanche",
};
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Fetch viewport GeoJSON for each visible hazard layer on moveend (debounced). */
export function useViewportLayers(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  layerState: LayerStateMap,
  ready: boolean,
) {
  const timer = useRef<number | null>(null);
  const lastKey = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    if (!map) return;

    const refresh = async () => {
      const b = map.getBounds();
      const bbox = { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() };
      const key = `${bbox.west.toFixed(2)},${bbox.south.toFixed(2)},${bbox.east.toFixed(2)},${bbox.north.toFixed(2)}`;
      for (const id of Object.keys(VIEWPORT_SOURCES)) {
        const visible = !!layerState[id]?.visible;
        const src = map.getSource(VIEWPORT_SOURCES[id].source) as maplibregl.GeoJSONSource | undefined;
        if (!src) continue;
        if (!visible) { src.setData(EMPTY); lastKey.current[id] = ""; continue; }
        if (lastKey.current[id] === key) continue;       // same view, already loaded
        lastKey.current[id] = key;
        try {
          const res = await api.layerData(LAYER_API_ID[id], bbox);
          src.setData({ type: "FeatureCollection", features: res.features || [] });
        } catch {
          src.setData(EMPTY);
        }
      }
    };

    const onMove = () => {
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(refresh, 400);
    };
    map.on("moveend", onMove);
    refresh(); // initial + on layerState change
    return () => { map.off("moveend", onMove); if (timer.current) window.clearTimeout(timer.current); };
  }, [mapRef, layerState, ready]);
}
