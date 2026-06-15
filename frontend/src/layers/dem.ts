const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

export type DemEncoding = "terrarium" | "mapbox";

export interface DemSourceConfig {
  tiles: string[];
  encoding: DemEncoding;
  tileSize: number;
  maxzoom: number;
  attribution: string;
}

/** Free AWS Terrarium by default; MapTiler terrain-RGB when a key is set. */
export function getDemSource(): DemSourceConfig {
  if (MAPTILER_KEY) {
    return {
      tiles: [`https://api.maptiler.com/tiles/terrain-rgb-v2/{z}/{x}/{y}.webp?key=${MAPTILER_KEY}`],
      encoding: "mapbox",
      tileSize: 256,
      maxzoom: 12,   // MapTiler terrain-RGB tops out at z12; Terrarium goes to 15
      attribution: "© MapTiler © OpenStreetMap contributors",
    };
  }
  return {
    tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
    encoding: "terrarium",
    tileSize: 256,
    maxzoom: 15,
    attribution: "Elevation: Mapzen/Terrarium, SRTM, USGS",
  };
}
