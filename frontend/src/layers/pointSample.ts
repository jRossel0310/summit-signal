// On-device DEM point sampling: shared tile cache + elevation/slope-aspect at a
// coordinate. Lifted from MapView's hover reader; the single source for point
// elevation queries (hover readout + dashboard slope/aspect). No metered API.
import { getDemSource, type DemEncoding } from "./dem";
import {
  decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel,
  aspectCompass, slopeBucketLabel,
} from "./terrainMath";

const DEM = getDemSource();
const TILE = 256;
const SAMPLE_Z = Math.min(DEM.maxzoom, 12);
const CACHE_MAX = 256;

export interface SlopeAspectSample {
  slope_deg: number;
  aspect_deg: number;
  aspect_compass: string;
  slope_bucket: string;
}

const tiles = new Map<string, Float32Array | "error">();
const inflight = new Map<string, Promise<Float32Array | null>>();

const tileKey = (z: number, x: number, y: number) => `${z}/${x}/${y}`;

/** RGBA ImageData bytes -> Float32Array of elevations (m). Pure; canvas-free. */
export function decodeTileFromImageData(data: Uint8ClampedArray, encoding: DemEncoding): Float32Array {
  const decode = encoding === "terrarium" ? decodeTerrarium : decodeMapbox;
  const out = new Float32Array(data.length / 4);
  for (let i = 0; i < out.length; i++) out[i] = decode(data[i * 4], data[i * 4 + 1], data[i * 4 + 2]);
  return out;
}

function evict() {
  while (tiles.size > CACHE_MAX) {
    const oldest = tiles.keys().next().value;
    if (oldest === undefined) break;
    tiles.delete(oldest);
  }
}

async function ensureTile(z: number, x: number, y: number): Promise<Float32Array | null> {
  const key = tileKey(z, x, y);
  const cached = tiles.get(key);
  if (cached instanceof Float32Array) return cached;
  if (cached === "error") return null;
  const existing = inflight.get(key);
  if (existing) return existing;
  const url = DEM.tiles[0].replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  const p = (async () => {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error("dem tile http " + r.status);
      const bmp = await createImageBitmap(await r.blob());
      const c = document.createElement("canvas");
      c.width = TILE; c.height = TILE;
      const cx = c.getContext("2d")!;
      cx.drawImage(bmp, 0, 0, TILE, TILE);
      const arr = decodeTileFromImageData(cx.getImageData(0, 0, TILE, TILE).data, DEM.encoding);
      tiles.set(key, arr); evict();
      return arr;
    } catch {
      tiles.set(key, "error");
      return null;
    } finally {
      inflight.delete(key);
    }
  })();
  inflight.set(key, p);
  return p;
}

function cachedTile(z: number, x: number, y: number): Float32Array | null {
  const cached = tiles.get(tileKey(z, x, y));
  if (cached instanceof Float32Array) return cached;
  if (cached === undefined) void ensureTile(z, x, y); // warm it; ignore the promise
  return null;
}

/** Fractional web-mercator tile + clamped pixel for a coord at zoom z (256px tiles). */
export function lngLatToTilePixel(lng: number, lat: number, z: number) {
  const n = 2 ** z;
  const xf = ((lng + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const yf = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  const tx = Math.floor(xf), ty = Math.floor(yf);
  const px = Math.min(TILE - 1, Math.max(0, Math.floor((xf - tx) * TILE)));
  const py = Math.min(TILE - 1, Math.max(0, Math.floor((yf - ty) * TILE)));
  return { tx, ty, px, py };
}

/** Slope/aspect from a decoded tile at pixel (px,py). Clamps to [1, TILE-2] so the
 *  3x3 neighbourhood stays in-tile. Pure. */
export function slopeAspectAt(tile: Float32Array, px: number, py: number, lat: number, z: number): SlopeAspectSample {
  const cx = Math.min(TILE - 2, Math.max(1, px));
  const cy = Math.min(TILE - 2, Math.max(1, py));
  const at = (x: number, y: number) => tile[y * TILE + x];
  const spacing = metersPerPixel(lat, z);
  const { slope, aspect } = pixelSlopeAspect(
    at(cx, cy), at(cx, cy - 1), at(cx + 1, cy), at(cx, cy + 1), at(cx - 1, cy), spacing,
  );
  return {
    slope_deg: Math.round(slope * 10) / 10,
    aspect_deg: Math.round(aspect * 10) / 10,
    aspect_compass: aspectCompass(aspect),
    slope_bucket: slopeBucketLabel(slope),
  };
}

/** Best-effort elevation (m) at a coord from cached DEM tiles; null if not loaded. */
export function elevationAtM(lng: number, lat: number): number | null {
  const { tx, ty, px, py } = lngLatToTilePixel(lng, lat, SAMPLE_Z);
  const tile = cachedTile(SAMPLE_Z, tx, ty);
  return tile ? tile[py * TILE + px] : null;
}

/** Slope/aspect at a coord from the on-device DEM; null if the tile can't load. */
export async function sampleSlopeAspect(lng: number, lat: number): Promise<SlopeAspectSample | null> {
  try {
    const { tx, ty, px, py } = lngLatToTilePixel(lng, lat, SAMPLE_Z);
    const tile = await ensureTile(SAMPLE_Z, tx, ty);
    if (!tile) return null;
    return slopeAspectAt(tile, px, py, lat, SAMPLE_Z);
  } catch {
    return null;
  }
}

// --- test seam (used only by pointSample.test.ts; no fetch/canvas in tests) ---
export function __primeTileForTest(z: number, x: number, y: number, arr: Float32Array): void {
  tiles.set(tileKey(z, x, y), arr);
}
export function __resetTilesForTest(): void { tiles.clear(); inflight.clear(); }
