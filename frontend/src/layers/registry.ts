import type { LayerDescriptor } from "./types";

// Order matters: panel order, and (for overlays) MapLibre draw order.
export const LAYERS: LayerDescriptor[] = [
  // --- basemaps (pick-one) ---
  { id: "basemap.street", group: "basemap", kind: "basemap", label: "Street",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.satellite", group: "basemap", kind: "basemap", label: "Satellite",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.topo", group: "basemap", kind: "basemap", label: "Topo",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.hybrid", group: "basemap", kind: "basemap", label: "Hybrid (sat + labels)",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.dark", group: "basemap", kind: "basemap", label: "Dark",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },

  // --- overlays (migrated; multi-toggle) ---
  { id: "overlay.perimeters", group: "hazard", kind: "vector-overlay", label: "Fire perimeters",
    defaultVisible: true, defaultOpacity: 0.18, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#d84a1b", label: "Active perimeter" }] } },
  { id: "overlay.fires", group: "hazard", kind: "marker", label: "Active fires",
    defaultVisible: true, defaultOpacity: 0.75, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#ff5a1f", label: "VIIRS detection" }] } },
  { id: "overlay.gpx", group: "trip", kind: "vector-overlay", label: "GPX route",
    defaultVisible: true, defaultOpacity: 0.9, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#0f766e", label: "Route" }] } },
  { id: "overlay.savedTrips", group: "trip", kind: "marker", label: "Saved trips",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },
  { id: "overlay.point", group: "trip", kind: "marker", label: "Selected point",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },

  // --- coming soon (disabled previews) ---
  { id: "overlay.slope", group: "terrain", kind: "raster-overlay", label: "Slope angle",
    defaultVisible: false, defaultOpacity: 0.6, supportsOpacity: true, comingSoonPhase: 2 },
  { id: "overlay.hillshade", group: "terrain", kind: "raster-overlay", label: "Hillshade",
    defaultVisible: false, defaultOpacity: 0.6, supportsOpacity: true, comingSoonPhase: 2 },
  { id: "overlay.weather", group: "weather", kind: "data-overlay", label: "Weather / snow",
    providerId: "weather", defaultVisible: false, defaultOpacity: 1, supportsOpacity: false,
    comingSoonPhase: 3 },
];

export const BASEMAP_LAYERS = LAYERS.filter((l) => l.group === "basemap");
export const OVERLAY_LAYERS = LAYERS.filter((l) => l.group !== "basemap" && !l.comingSoonPhase);
export const COMING_SOON_LAYERS = LAYERS.filter((l) => !!l.comingSoonPhase);
