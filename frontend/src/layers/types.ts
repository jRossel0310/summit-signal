// Layer metadata, runtime state, and point-selection result types.
// Wire shape is snake_case to mirror the backend (see src/types.ts convention).

export type LayerKind =
  | "basemap"         // exclusive; swaps the map style
  | "raster-overlay"  // tiled raster over the basemap (Phase 2: slope/hillshade)
  | "vector-overlay"  // geojson lines/fills (perimeters, future trails)
  | "marker"          // geojson points w/ symbols (saved trips, fires, point)
  | "data-overlay";   // backed by a backend provider; also feeds the dashboard

export type LayerGroup =
  | "basemap" | "terrain" | "weather" | "hazard" | "reference" | "trip";

export interface Legend {
  kind: "swatches" | "gradient" | "wheel" | "none";
  items?: { color: string; label: string }[];
  note?: string;
}

export interface LayerDescriptor {
  id: string;
  group: LayerGroup;
  kind: LayerKind;
  label: string;
  description?: string;
  legend?: Legend;
  providerId?: string;      // data-overlay -> backend provider id
  requiresKey?: string;     // env var that unlocks/upgrades it
  defaultVisible: boolean;
  defaultOpacity: number;   // 0..1
  supportsOpacity: boolean;
  comingSoonPhase?: number; // if set, shown disabled in the "coming soon" group
  attribution?: string;
}

export interface LayerRuntimeState { visible: boolean; opacity: number; }
export type LayerStateMap = Record<string, LayerRuntimeState>;

export type SectionStatus =
  | "ok" | "loading" | "empty" | "needs-key" | "error" | "coming-soon";

export interface PointSection {
  layer_id: string;
  title: string;
  status: SectionStatus;
  data?: Record<string, unknown> | null;
  message?: string | null;
  source?: { name: string; url?: string | null; timestamp?: string | null } | null;
}

export interface SelectionResult {
  lat: number;
  lon: number;
  place_name?: string | null;
  sections: PointSection[];
}
