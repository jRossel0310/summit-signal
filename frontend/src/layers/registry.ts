import type { LayerDescriptor } from "./types";
import { SLOPE_BUCKETS } from "./terrainColors";

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
  { id: "overlay.perimeters", group: "hazard", kind: "data-overlay", label: "Fire perimeters",
    description: "Mapped boundaries of active large fires (WFIGS). Indicative — verify with official sources.",
    providerId: "wildfire", defaultVisible: false, defaultOpacity: 0.18, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#d84a1b", label: "Active perimeter" }] } },
  { id: "overlay.fires", group: "hazard", kind: "data-overlay", label: "Active fires",
    description: "Recent satellite (VIIRS) heat detections — indicative points, not official fire boundaries.",
    providerId: "wildfire", defaultVisible: false, defaultOpacity: 0.75, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#ff5a1f", label: "VIIRS detection" }] } },
  { id: "overlay.gpx", group: "trip", kind: "vector-overlay", label: "GPX route",
    description: "The route attached to the selected trip — an uploaded or in-app-built GPX line.",
    defaultVisible: true, defaultOpacity: 0.9, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#0f766e", label: "Route" }] } },
  { id: "overlay.savedTrips", group: "trip", kind: "marker", label: "Saved trips",
    description: "Markers for your saved trip points. Click one to select that trip.",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },
  { id: "overlay.point", group: "trip", kind: "marker", label: "Selected point",
    description: "The point you last clicked or searched — used for the point panel and for new trips.",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },

  // --- terrain (Phase 2; draw order bottom->top: hillshade, slope, aspect, contours) ---
  { id: "overlay.terrain3d", group: "terrain", kind: "terrain-3d", label: "3D terrain",
    description: "Tilts the camera and drapes the map over real elevation (DEM) so terrain rises in relief. Heavier on the GPU.",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false, legend: { kind: "none" } },
  { id: "overlay.hillshade", group: "terrain", kind: "raster-overlay", label: "Hillshade",
    description: "Shaded relief that makes ridges, valleys, and terrain shape easy to read.",
    defaultVisible: false, defaultOpacity: 0.45, supportsOpacity: true,
    legend: { kind: "none" } },
  { id: "overlay.slope", group: "terrain", kind: "raster-overlay", label: "Slope angle",
    description: "Shades terrain steepness; reds (about 35°+) flag avalanche- and fall-prone slopes.",
    defaultVisible: false, defaultOpacity: 0.55, supportsOpacity: true,
    legend: { kind: "swatches", items: SLOPE_BUCKETS.map((b) => ({ color: b.color, label: b.label })) } },
  { id: "overlay.aspect", group: "terrain", kind: "raster-overlay", label: "Aspect",
    description: "Colors the compass direction each slope faces — useful for sun, snow, and wind exposure.",
    defaultVisible: false, defaultOpacity: 0.55, supportsOpacity: true,
    legend: { kind: "wheel" } },
  { id: "overlay.contours", group: "terrain", kind: "vector-overlay", label: "Contours",
    description: "Elevation contour lines (40 ft, with 200 ft index lines labeled).",
    defaultVisible: false, defaultOpacity: 0.8, supportsOpacity: true,
    legend: { kind: "swatches", note: "40 ft / 200 ft index", items: [{ color: "#7a5a3a", label: "contour" }] } },

  // --- hazard data-overlays ---
  { id: "overlay.aqi", group: "hazard", kind: "data-overlay", label: "Air quality (AQI)",
    description: "Air-quality index from nearby ground stations — higher and redder means worse air.",
    providerId: "aqi", defaultVisible: false, defaultOpacity: 0.85, supportsOpacity: true,
    legend: { kind: "swatches", items: [
      { color: "#00e400", label: "Good" }, { color: "#ffff00", label: "Mod" },
      { color: "#ff7e00", label: "USG" }, { color: "#ff0000", label: "Unhealthy" },
      { color: "#8f3f97", label: "V.Unhealthy" }, { color: "#7e0023", label: "Hazard" }] } },
  { id: "overlay.avalanche", group: "hazard", kind: "data-overlay", label: "Avalanche danger",
    description: "Regional avalanche danger rating where a forecast center publishes it. Always read the official forecast.",
    providerId: "avalanche", defaultVisible: false, defaultOpacity: 0.4, supportsOpacity: true,
    legend: { kind: "swatches", items: [
      { color: "#52ba4a", label: "Low" }, { color: "#fff300", label: "Mod" },
      { color: "#f7941e", label: "Consid." }, { color: "#ed1c24", label: "High" },
      { color: "#231f20", label: "Extreme" }] } },

  // --- weather data-overlay (feeds the point panel only; no map render) ---
  { id: "overlay.snow", group: "weather", kind: "data-overlay", label: "Snow depth (point panel)",
    description: "Adds modeled snow depth to the point panel; it does not draw on the map.",
    providerId: "snow", defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
];

export const BASEMAP_LAYERS = LAYERS.filter((l) => l.group === "basemap");
export const OVERLAY_LAYERS = LAYERS.filter((l) => l.group !== "basemap" && !l.comingSoonPhase);
export const COMING_SOON_LAYERS = LAYERS.filter((l) => !!l.comingSoonPhase);
