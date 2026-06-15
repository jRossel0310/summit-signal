import type maplibregl from "maplibre-gl";

const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

export type BasemapId =
  | "basemap.street" | "basemap.satellite" | "basemap.topo"
  | "basemap.hybrid" | "basemap.dark";

const ESRI_IMAGERY =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_REF =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";

function raster(tiles: string[], attribution: string): maplibregl.StyleSpecification {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: { base: { type: "raster", tiles, tileSize: 256, attribution } },
    layers: [{ id: "base", type: "raster", source: "base" }],
  };
}

const FREE: Record<BasemapId, maplibregl.StyleSpecification> = {
  "basemap.street": raster(
    ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors",
  ),
  "basemap.topo": raster(
    ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
  ),
  "basemap.satellite": raster([ESRI_IMAGERY], "Imagery © Esri"),
  "basemap.hybrid": {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      img: { type: "raster", tiles: [ESRI_IMAGERY], tileSize: 256, attribution: "Imagery © Esri" },
      ref: { type: "raster", tiles: [ESRI_REF], tileSize: 256, attribution: "© Esri" },
    },
    layers: [
      { id: "img", type: "raster", source: "img" },
      { id: "ref", type: "raster", source: "ref" },
    ],
  },
  "basemap.dark": raster(
    ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors © CARTO",
  ),
};

// MapTiler style ids used when a key is configured (free tier covers low usage).
const MAPTILER_STYLE: Record<BasemapId, string> = {
  "basemap.street": "streets-v2",
  "basemap.topo": "outdoor-v2",
  "basemap.satellite": "satellite",
  "basemap.hybrid": "hybrid",
  "basemap.dark": "dataviz-dark",
};

export function hasBasemapKey(): boolean {
  return !!MAPTILER_KEY;
}

/** Returns a MapLibre style: a MapTiler style URL when a key is set, else a
 *  free no-key raster style. Both are accepted by map.setStyle(). */
export function getBasemapStyle(id: BasemapId): maplibregl.StyleSpecification | string {
  if (MAPTILER_KEY) {
    return `https://api.maptiler.com/maps/${MAPTILER_STYLE[id]}/style.json?key=${MAPTILER_KEY}`;
  }
  return FREE[id];
}
