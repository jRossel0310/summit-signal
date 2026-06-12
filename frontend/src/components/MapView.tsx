import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Trip } from "../types";

export interface LayerState {
  basemap: "topo" | "street";
  selectedPoint: boolean;
  gpxRoute: boolean;
  fires: boolean;
  perimeters: boolean;
  savedTrips: boolean;
}

export interface FireDetection {
  latitude: number;
  longitude: number;
  distance_miles?: number;
  confidence?: string | number;
  acq_date?: string;
}

interface Props {
  layers: LayerState;
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

const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";

const STREET_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: GLYPHS,
  sources: {
    base: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "base", type: "raster", source: "base" }],
};

const TOPO_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: GLYPHS,
  sources: {
    base: {
      type: "raster",
      tiles: ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
    },
  },
  layers: [{ id: "base", type: "raster", source: "base" }],
};

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export default function MapView({
  layers, trips, selectedTripId, selectedPoint, flyTo, gpxPoints,
  fireDetections, perimeterGeojson, onSelectPoint, onSelectTrip,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const readyRef = useRef(false);
  // Keep latest handlers without re-binding map events.
  const handlersRef = useRef({ onSelectPoint, onSelectTrip });
  handlersRef.current = { onSelectPoint, onSelectTrip };

  // ---- init once ----
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: layers.basemap === "topo" ? TOPO_STYLE : STREET_STYLE,
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
    // Re-add overlays after any style swap.
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
    setVisible(["trips-circle", "trips-label"], layers.savedTrips);
    setVisible(["gpx-line"], layers.gpxRoute);
    setVisible(["fires-circle"], layers.fires);
    setVisible(["perims-fill", "perims-line"], layers.perimeters);
  }
  function syncMarker() {
    const map = mapRef.current;
    if (!map) return;
    if (selectedPoint && layers.selectedPoint) {
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
  useEffect(() => { if (readyRef.current) syncVisibility(); }, [layers]);
  useEffect(() => { syncMarker(); }, [selectedPoint, layers.selectedPoint]);

  // basemap swap
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.setStyle(layers.basemap === "topo" ? TOPO_STYLE : STREET_STYLE);
  }, [layers.basemap]);

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
