import mlcontour from "maplibre-contour";
import type maplibregl from "maplibre-gl";
import type { DemSourceConfig } from "./dem";

let demSource: InstanceType<typeof mlcontour.DemSource> | null = null;

/** One-time: register maplibre-contour's protocol over the active DEM. */
export function setupContours(mlgl: typeof maplibregl, dem: DemSourceConfig) {
  if (demSource) return;
  demSource = new mlcontour.DemSource({
    url: dem.tiles[0],
    encoding: dem.encoding,
    maxzoom: dem.maxzoom,
    worker: true,
  });
  demSource.setupMaplibre(mlgl);
}

/** Vector tile URL for the contour source (feet; 40 ft minor / 200 ft index). */
export function contourTilesUrl(): string {
  if (!demSource) throw new Error("setupContours must run first");
  return demSource.contourProtocolUrl({
    multiplier: 3.28084, // meters -> feet
    thresholds: {
      10: [200, 1000],
      12: [80, 400],
      14: [40, 200],
    },
    elevationKey: "ele",
    levelKey: "level",
    contourLayer: "contours",
  });
}
