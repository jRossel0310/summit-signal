import { describe, it, expect, beforeEach } from "vitest";
import {
  decodeTileFromImageData, lngLatToTilePixel, slopeAspectAt, sampleSlopeAspect,
  __primeTileForTest, __resetTilesForTest, type SlopeAspectSample,
} from "./pointSample";

const TILE = 256;

function flatTile(elev: number): Float32Array {
  return new Float32Array(TILE * TILE).fill(elev);
}
// Elevation rises toward the EAST (increasing x) -> terrain faces downhill WEST.
function eastRisingTile(): Float32Array {
  const a = new Float32Array(TILE * TILE);
  for (let y = 0; y < TILE; y++) for (let x = 0; x < TILE; x++) a[y * TILE + x] = x * 10;
  return a;
}

beforeEach(() => __resetTilesForTest());

describe("decodeTileFromImageData", () => {
  it("decodes terrarium sea level from RGBA bytes", () => {
    const data = new Uint8ClampedArray([128, 0, 0, 255, 128, 0, 0, 255]);
    const arr = decodeTileFromImageData(data, "terrarium");
    expect(arr.length).toBe(2);
    expect(arr[0]).toBeCloseTo(0, 5);
  });
});

describe("lngLatToTilePixel", () => {
  it("keeps pixel coords within [0, TILE)", () => {
    const { px, py } = lngLatToTilePixel(-105.0, 40.0, 12);
    expect(px).toBeGreaterThanOrEqual(0);
    expect(px).toBeLessThan(TILE);
    expect(py).toBeGreaterThanOrEqual(0);
    expect(py).toBeLessThan(TILE);
  });
});

describe("slopeAspectAt", () => {
  it("flat tile -> 0 slope, 0–15 band", () => {
    const r = slopeAspectAt(flatTile(1000), 100, 100, 40, 12);
    expect(r.slope_deg).toBe(0);
    expect(r.slope_bucket).toBe("0–15°");
  });
  it("east-rising tile -> west-facing aspect", () => {
    const r = slopeAspectAt(eastRisingTile(), 100, 100, 40, 12);
    expect(r.slope_deg).toBeGreaterThan(0);
    expect(r.aspect_compass).toBe("W");
  });
  it("clamps edge pixels (no NaN at a tile border)", () => {
    const r = slopeAspectAt(eastRisingTile(), 0, 255, 40, 12);
    expect(Number.isFinite(r.slope_deg)).toBe(true);
    expect(Number.isFinite(r.aspect_deg)).toBe(true);
  });
});

describe("sampleSlopeAspect", () => {
  it("computes from a primed tile without fetching", async () => {
    const { tx, ty } = lngLatToTilePixel(-105.0, 40.0, 12);
    __primeTileForTest(12, tx, ty, eastRisingTile());
    const r = await sampleSlopeAspect(-105.0, 40.0);
    expect(r).not.toBeNull();
    expect((r as SlopeAspectSample).aspect_compass).toBe("W");
  });
});
