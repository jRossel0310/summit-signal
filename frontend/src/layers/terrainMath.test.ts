import { describe, it, expect } from "vitest";
import { decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel } from "./terrainMath";

describe("DEM decode", () => {
  it("decodes terrarium sea level (32768,0,0 -> 0m)", () => {
    expect(decodeTerrarium(128, 0, 0)).toBeCloseTo(0, 5); // 128*256 = 32768 -> -32768 +32768 = 0
  });
  it("decodes mapbox base (-10000m at 0,0,0)", () => {
    expect(decodeMapbox(0, 0, 0)).toBeCloseTo(-10000, 5);
  });
});

describe("pixelSlopeAspect", () => {
  it("flat -> 0 slope", () => {
    const { slope } = pixelSlopeAspect(100, 100, 100, 100, 100, 30);
    expect(slope).toBe(0);
  });
  it("east-facing -> ~90 aspect", () => {
    // east lower, west higher
    const { slope, aspect } = pixelSlopeAspect(100, 100, 50, 100, 150, 30);
    expect(slope).toBeGreaterThan(0);
    expect(Math.abs(aspect - 90)).toBeLessThan(0.5);
  });
});

describe("metersPerPixel", () => {
  it("is positive and shrinks with zoom", () => {
    const z5 = metersPerPixel(40, 5);
    const z12 = metersPerPixel(40, 12);
    expect(z5).toBeGreaterThan(z12);
    expect(z12).toBeGreaterThan(0);
  });
});
