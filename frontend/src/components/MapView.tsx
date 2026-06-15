import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Trip } from "../types";
import type { LayerStateMap } from "../layers/types";
import { getBasemapStyle, type BasemapId } from "../layers/basemaps";
import { activeBasemapId } from "../layers/layerState";

export interface FireDetection {
  latitude: number;
  longitude: number;
  distance_miles?: number;
  confidence?: string | number;
  acq_date?: string;
}

// Maps a registry overlay id -> its MapLibre layer ids + opacity paint props.
const OVERLAY_RENDER: Record<string, { layerIds: string[]; opacity?: [string, string][] }> = {
  "overlay.perimeters": {
    layerIds: ["perims-fill", "perims-line"],
    opacity: [["perims-fill", "fill-opacity"], ["perims-line", "line-opacity"]],
  },
  "overlay.fires": {
    layerIds: ["fires-circle"],
    opacity: [["fires-circle", "circle-opacity"]],
  },
  "overlay.gpx": {
    layerIds: ["gpx-line"],
    opacity: [["gpx-line", "line-opacity"]],
  },
  "overlay.savedTrips": {
    layerIds: ["trips-circle", "trips-label"],
  },
};

interface Props {
  layerState: LayerStateMap;
  trips: Trip[];
  selectedTripId: number | null;
  selectedPoint: { lat: number; lon: number } | null;
  flyTo: { lat: number; lon: number; zoom?: number } | null;
  gpxPoints: [number, number, number | null][] | null; // [lat, lon, ele]
  fireDetections: FireDetection[];
  perimeterGeojson: GeoJSON.FeatureCollection | null;
  onSelectPoint: (lat: number, lon: number) => void;
  onSelectTrip: (id: number) => void;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export default function MapView({
  layerState, trips, selectedTripId, selectedPoint, flyTo, gpxPoints,
  fireDetections, perimeterGeojson, onSelectPoint, onSelectTrip,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const readyRef = useRef(false);
  const activeBaseRef = useRef<string>(activeBasemapId(layerState));
  const handlersRef = useRef({ onSelectPoint, onSelectTrip });
  handlersRef.current = { onSelectPoint, onSelectTrip };

  // ---- init once ----
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: getBasemapStyle(activeBasemapId(layerState) as BasemapId),
      center: [-110.5, 41.5],
      zoom: 4,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    map.on("load", () => {
      addOverlaySources(map);
      readyRef.current = true;
      syncAll();
    });
    map.on("styledata", () => {
      if (!readyRef.current) return;
      if (!map.getSource("trips")) {
        addOverlaySources(map);
        syncAll();
      }
    });

    map.on("click", (e) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: ["trips-circle"] });
      if (feats.length > 0) {
        const id = feats[0].properties?.id;
        if (id != null) handlersRef.current.onSelectTrip(Number(id));
        return;
      }
      handlersRef.current.onSelectPoint(e.lngLat.lat, e.lngLat.lng);
    });

    map.on("mouseenter", "trips-circle", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "trips-circle", () => (map.getCanvas().style.cursor = ""));
    map.on("click", "fires-circle", (e) => {
      const p = e.features?.[0]?.properties || {};
      new maplibregl.Popup({ closeButton: false })
        .setLngLat(e.lngLat)
        .setHTML(
          `<div class="p-title">Active fire detection</div>
           <div class="p-meta">date: ${p.acq_date || "?"} · conf: ${p.confidence ?? "?"} · ${p.distance_miles != null ? Number(p.distance_miles).toFixed(1) + " mi away" : ""}</div>`,
        )
        .addTo(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addOverlaySources(map: maplibregl.Map) {
    if (map.getSource("trips")) return;
    map.addSource("trips", { type: "geojson", data: EMPTY_FC });
    map.addSource("gpx", { type: "geojson", data: EMPTY_FC });
    map.addSource("fires", { type: "geojson", data: EMPTY_FC });
    map.addSource("perims", { type: "geojson", data: EMPTY_FC });

    map.addLayer({
      id: "perims-fill", type: "fill", source: "perims",
      paint: { "fill-color": "#d84a1b", "fill-opacity": 0.18 },
    });
    map.addLayer({
      id: "perims-line", type: "line", source: "perims",
      paint: { "line-color": "#d84a1b", "line-width": 1.6, "line-dasharray": [3, 2] },
    });
    map.addLayer({
      id: "fires-circle", type: "circle", source: "fires",
      paint: {
        "circle-radius": 6, "circle-color": "#ff5a1f", "circle-opacity": 0.75,
        "circle-stroke-color": "#7c1d05", "circle-stroke-width": 1.4,
      },
    });
    map.addLayer({
      id: "gpx-line", type: "line", source: "gpx",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#0f766e", "line-width": 3.2, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "trips-circle", type: "circle", source: "trips",
      paint: {
        "circle-radius": ["case", ["get", "selected"], 9, 7],
        "circle-color": ["case", ["get", "selected"], "#d84a1b", "#1f241f"],
        "circle-stroke-color": "#fbfaf6", "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "trips-label", type: "symbol", source: "trips",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-offset": [0, 1.3],
        "text-anchor": "top",
        "text-font": ["Noto Sans Regular"],
        "text-optional": true,
      },
      paint: { "text-color": "#1f241f", "text-halo-color": "#fbfaf6", "text-halo-width": 1.4 },
    });
  }

  function setData(id: string, data: GeoJSON.FeatureCollection) {
    const src = mapRef.current?.getSource(id) as maplibregl.GeoJSONSource | undefined;
    src?.setData(data);
  }

  function setVisible(layerIds: string[], visible: boolean) {
    const map = mapRef.current;
    if (!map) return;
    for (const id of layerIds) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    }
  }

  function syncAll() {
    syncTrips(); syncGpx(); syncFires(); syncPerims(); syncVisibility(); syncMarker();
  }

  function syncTrips() {
    setData("trips", {
      type: "FeatureCollection",
      features: trips.map((t) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [t.longitude, t.latitude] },
        properties: { id: t.id, name: t.name, selected: t.id === selectedTripId },
      })),
    });
  }
  function syncGpx() {
    if (!gpxPoints || gpxPoints.length < 2) { setData("gpx", EMPTY_FC); return; }
    setData("gpx", {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "LineString", coordinates: gpxPoints.map((p) => [p[1], p[0]]) },
        properties: {},
      }],
    });
  }
  function syncFires() {
    setData("fires", {
      type: "FeatureCollection",
      features: fireDetections.map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [f.longitude, f.latitude] },
        properties: {
          distance_miles: f.distance_miles, confidence: f.confidence, acq_date: f.acq_date,
        },
      })),
    });
  }
  function syncPerims() { setData("perims", perimeterGeojson || EMPTY_FC); }

  function syncVisibility() {
    const map = mapRef.current;
    if (!map) return;
    for (const [id, render] of Object.entries(OVERLAY_RENDER)) {
      const st = layerState[id];
      setVisible(render.layerIds, !!st?.visible);
      if (render.opacity && st) {
        for (const [layerId, prop] of render.opacity) {
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, prop, st.opacity);
        }
      }
    }
  }

  function syncMarker() {
    const map = mapRef.current;
    if (!map) return;
    const pointVisible = layerState["overlay.point"]?.visible ?? true;
    if (selectedPoint && pointVisible) {
      if (!markerRef.current) {
        const el = document.createElement("div");
        el.innerHTML =
          `<svg width="28" height="34" viewBox="0 0 28 34"><path d="M14 0C6.8 0 1 5.8 1 13c0 9.6 13 21 13 21s13-11.4 13-21C27 5.8 21.2 0 14 0z" fill="#d84a1b" stroke="#7c1d05" stroke-width="1.4"/><circle cx="14" cy="13" r="4.6" fill="#fbfaf6"/></svg>`;
        markerRef.current = new maplibregl.Marker({ element: el, anchor: "bottom" });
      }
      markerRef.current.setLngLat([selectedPoint.lon, selectedPoint.lat]).addTo(map);
    } else {
      markerRef.current?.remove();
    }
  }

  // ---- prop-driven syncs ----
  useEffect(() => { if (readyRef.current) syncTrips(); }, [trips, selectedTripId]);
  useEffect(() => { if (readyRef.current) syncGpx(); }, [gpxPoints]);
  useEffect(() => { if (readyRef.current) syncFires(); }, [fireDetections]);
  useEffect(() => { if (readyRef.current) syncPerims(); }, [perimeterGeojson]);
  useEffect(() => { if (readyRef.current) syncVisibility(); }, [layerState]);
  useEffect(() => { syncMarker(); }, [selectedPoint, layerState]);

  // basemap swap (only when the active basemap actually changes)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const next = activeBasemapId(layerState);
    if (next !== activeBaseRef.current) {
      activeBaseRef.current = next;
      map.setStyle(getBasemapStyle(next as BasemapId));
    }
  }, [layerState]);

  // fly to target
  useEffect(() => {
    if (!flyTo || !mapRef.current) return;
    mapRef.current.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: flyTo.zoom ?? 11, duration: 1400 });
  }, [flyTo]);

  return (
    <>
      <div ref={containerRef} className="map-container" />
      {selectedPoint && (
        <div className="coord-readout">
          {selectedPoint.lat.toFixed(5)}, {selectedPoint.lon.toFixed(5)}
        </div>
      )}
      <div className="map-overlay-br">click map to set trip point</div>
    </>
  );
}
