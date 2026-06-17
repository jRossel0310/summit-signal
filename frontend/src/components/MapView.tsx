import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Trip } from "../types";
import type { LayerStateMap } from "../layers/types";
import { getBasemapStyle, type BasemapId } from "../layers/basemaps";
import { useViewportLayers } from "../hooks/useViewportLayers";
import { activeBasemapId } from "../layers/layerState";
import { getDemSource } from "../layers/dem";
import { registerTerrainProtocols } from "../layers/terrainProtocol";
import { setupContours, contourTilesUrl } from "../layers/contours";
import { elevationAtM } from "../layers/pointSample";

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
  "overlay.fires": { layerIds: ["fires-circle"], opacity: [["fires-circle", "circle-opacity"]] },
  "overlay.gpx": { layerIds: ["gpx-line"], opacity: [["gpx-line", "line-opacity"]] },
  "overlay.savedTrips": { layerIds: ["trips-circle", "trips-label"] },
  "overlay.hillshade": { layerIds: ["hillshade"], opacity: [["hillshade", "hillshade-exaggeration"]] },
  "overlay.slope": { layerIds: ["slope-raster"], opacity: [["slope-raster", "raster-opacity"]] },
  "overlay.aspect": { layerIds: ["aspect-raster"], opacity: [["aspect-raster", "raster-opacity"]] },
  "overlay.contours": { layerIds: ["contour-lines", "contour-labels"], opacity: [["contour-lines", "line-opacity"]] },
  "overlay.aqi": { layerIds: ["aqi-circle"], opacity: [["aqi-circle", "circle-opacity"]] },
  "overlay.avalanche": { layerIds: ["avy-fill", "avy-line"], opacity: [["avy-fill", "fill-opacity"]] },
};

const DEM = getDemSource();
let terrainProtocolsReady = false;

interface Props {
  layerState: LayerStateMap;
  trips: Trip[];
  selectedTripId: number | null;
  selectedPoint: { lat: number; lon: number } | null;
  flyTo: { lat: number; lon: number; zoom?: number } | null;
  gpxPoints: [number, number, number | null][] | null; // [lat, lon, ele]
  onSelectPoint: (lat: number, lon: number) => void;
  onSelectTrip: (id: number) => void;
  // route builder (additive; all optional so existing usage is unaffected)
  routeMode?: boolean;
  routeWaypoints?: { lat: number; lon: number }[];
  routeSnappedPoints?: [number, number, number | null][] | null;
  onRouteAddWaypoint?: (lat: number, lon: number) => void;
  onRouteMoveWaypoint?: (index: number, lat: number, lon: number) => void;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export default function MapView({
  layerState, trips, selectedTripId, selectedPoint, flyTo, gpxPoints,
  onSelectPoint, onSelectTrip,
  routeMode = false, routeWaypoints = [], routeSnappedPoints = null,
  onRouteAddWaypoint, onRouteMoveWaypoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const readyRef = useRef(false);
  const activeBaseRef = useRef<string>(activeBasemapId(layerState));
  const hoverElevRef = useRef<HTMLDivElement | null>(null);
  const handlersRef = useRef({ onSelectPoint, onSelectTrip });
  handlersRef.current = { onSelectPoint, onSelectTrip };
  const routeRef = useRef({ routeMode, onRouteAddWaypoint, onRouteMoveWaypoint });
  routeRef.current = { routeMode, onRouteAddWaypoint, onRouteMoveWaypoint };
  const wpMarkersRef = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);

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
      setReady(true);
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
      if (routeRef.current.routeMode) {
        routeRef.current.onRouteAddWaypoint?.(e.lngLat.lat, e.lngLat.lng);
        return;
      }
      handlersRef.current.onSelectPoint(e.lngLat.lat, e.lngLat.lng);
    });

    map.on("mouseenter", "trips-circle", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "trips-circle", () => (map.getCanvas().style.cursor = ""));
    map.on("mousemove", (e) => {
      const el = hoverElevRef.current;
      if (!el) return;
      const terrainOn = ["overlay.hillshade", "overlay.slope", "overlay.aspect", "overlay.contours"]
        .some((id) => map.getLayer(OVERLAY_RENDER[id].layerIds[0]) &&
          map.getLayoutProperty(OVERLAY_RENDER[id].layerIds[0], "visibility") === "visible");
      if (!terrainOn) { el.style.display = "none"; return; }
      const m = elevationAtM(e.lngLat.lng, e.lngLat.lat);
      if (m == null) { el.style.display = "none"; return; }
      el.style.display = "block";
      el.style.left = `${e.point.x + 12}px`;
      el.style.top = `${e.point.y + 12}px`;
      el.textContent = `${Math.round(m * 3.28084).toLocaleString()} ft`;
    });
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
      for (const m of wpMarkersRef.current) m.remove();
      wpMarkersRef.current = [];
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
    map.addSource("aqi", { type: "geojson", data: EMPTY_FC });
    map.addLayer({ id: "aqi-circle", type: "circle", source: "aqi", layout: { visibility: "none" },
      paint: { "circle-radius": 7,
        "circle-color": ["step", ["coalesce", ["get", "aqi"], 0], "#00e400", 51, "#ffff00", 101, "#ff7e00", 151, "#ff0000", 201, "#8f3f97", 301, "#7e0023"],
        "circle-stroke-color": "#1f241f", "circle-stroke-width": 1, "circle-opacity": 0.85 } });
    map.addSource("avy", { type: "geojson", data: EMPTY_FC });
    map.addLayer({ id: "avy-fill", type: "fill", source: "avy", layout: { visibility: "none" },
      paint: { "fill-opacity": 0.4,
        "fill-color": ["match", ["downcase", ["coalesce", ["to-string", ["get", "danger"]], ""]],
          "low", "#52ba4a", "moderate", "#fff300", "considerable", "#f7941e",
          "high", "#ed1c24", "extreme", "#231f20", "#9aa395"] } });
    map.addLayer({ id: "avy-line", type: "line", source: "avy", layout: { visibility: "none" },
      paint: { "line-color": "#1f241f", "line-width": 0.6, "line-opacity": 0.5 } });
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
    map.addSource("route-builder-line", { type: "geojson", data: EMPTY_FC });
    map.addLayer({
      id: "route-builder-line-manual", type: "line", source: "route-builder-line",
      filter: ["==", ["get", "kind"], "manual"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#8a5a12", "line-width": 2.2, "line-dasharray": [2, 2], "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "route-builder-line-snapped", type: "line", source: "route-builder-line",
      filter: ["==", ["get", "kind"], "snapped"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#1d6fd8", "line-width": 4, "line-opacity": 0.95 },
    });
    map.addSource("route-builder-waypoints", { type: "geojson", data: EMPTY_FC });
    map.addLayer({
      id: "route-builder-waypoints", type: "circle", source: "route-builder-waypoints",
      paint: {
        "circle-radius": 8, "circle-color": "#1d6fd8",
        "circle-stroke-color": "#fbfaf6", "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "route-builder-labels", type: "symbol", source: "route-builder-waypoints",
      layout: {
        "text-field": ["get", "label"], "text-size": 11,
        "text-font": ["Noto Sans Regular"], "text-allow-overlap": true,
      },
      paint: { "text-color": "#fbfaf6" },
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

    // --- terrain (Phase 2) ---
    if (!terrainProtocolsReady) {
      registerTerrainProtocols(maplibregl, DEM);
      setupContours(maplibregl, DEM);
      terrainProtocolsReady = true;
    }
    map.addSource("dem", {
      type: "raster-dem", tiles: DEM.tiles, encoding: DEM.encoding,
      tileSize: DEM.tileSize, maxzoom: DEM.maxzoom, attribution: DEM.attribution,
    });
    map.addLayer({ id: "hillshade", type: "hillshade", source: "dem",
      paint: { "hillshade-exaggeration": 0.45 }, layout: { visibility: "none" } });
    map.addSource("slope", { type: "raster", tiles: ["slope://{z}/{x}/{y}"], tileSize: 256, minzoom: 10, maxzoom: 22 });
    map.addLayer({ id: "slope-raster", type: "raster", source: "slope", minzoom: 10,
      paint: { "raster-opacity": 0.55 }, layout: { visibility: "none" } });
    map.addSource("aspect", { type: "raster", tiles: ["aspect://{z}/{x}/{y}"], tileSize: 256, minzoom: 10, maxzoom: 22 });
    map.addLayer({ id: "aspect-raster", type: "raster", source: "aspect", minzoom: 10,
      paint: { "raster-opacity": 0.55 }, layout: { visibility: "none" } });
    map.addSource("contours", { type: "vector", tiles: [contourTilesUrl()], maxzoom: DEM.maxzoom });
    map.addLayer({ id: "contour-lines", type: "line", source: "contours", "source-layer": "contours", minzoom: 10,
      paint: { "line-color": "#7a5a3a", "line-width": ["match", ["get", "level"], 1, 1.4, 0.6], "line-opacity": 0.8 },
      layout: { visibility: "none" } });
    map.addLayer({ id: "contour-labels", type: "symbol", source: "contours", "source-layer": "contours", minzoom: 13,
      filter: ["==", ["get", "level"], 1],
      layout: { "symbol-placement": "line", "text-field": ["concat", ["get", "ele"], " ft"], "text-size": 10,
        "text-font": ["Noto Sans Regular"], visibility: "none" },
      paint: { "text-color": "#5c4530", "text-halo-color": "#fbfaf6", "text-halo-width": 1.2 } });
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
    syncTrips(); syncGpx(); syncRouteLine(); syncWaypointMarkers(); syncVisibility(); syncMarker();
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

  function syncRouteLine() {
    const feats: GeoJSON.Feature[] = [];
    if (routeWaypoints.length >= 2) {
      feats.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: routeWaypoints.map((w) => [w.lon, w.lat]) },
        properties: { kind: "manual" },
      });
    }
    if (routeSnappedPoints && routeSnappedPoints.length >= 2) {
      feats.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: routeSnappedPoints.map((p) => [p[1], p[0]]) },
        properties: { kind: "snapped" },
      });
    }
    setData("route-builder-line", { type: "FeatureCollection", features: feats });
  }

  function syncWaypointMarkers() {
    const map = mapRef.current;
    if (!map) return;
    setData("route-builder-waypoints", {
      type: "FeatureCollection",
      features: routeWaypoints.map((w, i) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [w.lon, w.lat] },
        properties: { label: String(i + 1) },
      })),
    });
    for (const m of wpMarkersRef.current) m.remove();
    wpMarkersRef.current = [];
    if (!routeMode) return;
    // Transparent 20px HTML markers sit on top of the numbered circle layer to
    // provide a drag hit-target; they are torn down and rebuilt on every change.
    routeWaypoints.forEach((w, i) => {
      const el = document.createElement("div");
      el.style.width = "20px";
      el.style.height = "20px";
      el.style.borderRadius = "50%";
      el.style.cursor = "grab";
      const marker = new maplibregl.Marker({ element: el, draggable: true })
        .setLngLat([w.lon, w.lat])
        .addTo(map);
      marker.on("dragend", () => {
        const ll = marker.getLngLat();
        routeRef.current.onRouteMoveWaypoint?.(i, ll.lat, ll.lng);
      });
      wpMarkersRef.current.push(marker);
    });
  }

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
  useEffect(() => { if (readyRef.current) syncRouteLine(); }, [routeWaypoints, routeSnappedPoints]);
  useEffect(() => { if (readyRef.current) syncWaypointMarkers(); }, [routeWaypoints, routeMode]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.getCanvas().style.cursor = routeMode ? "crosshair" : "";
  }, [routeMode]);
  useEffect(() => { if (readyRef.current) syncVisibility(); }, [layerState]);
  useEffect(() => { syncMarker(); }, [selectedPoint, layerState]);
  useViewportLayers(mapRef, layerState, ready);

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
      <div ref={hoverElevRef} className="hover-elev" style={{ display: "none" }} />
    </>
  );
}
