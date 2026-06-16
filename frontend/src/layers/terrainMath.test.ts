import { describe, it, expect } from "vitest";
import {
  decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel,
  aspectCompass, slopeBucketLabel,
} from "./terrainMath";

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

describe("aspectCompass", () => {
  it("maps cardinals, diagonals, and wraps", () => {
    expect(aspectCompass(0)).toBe("N");
    expect(aspectCompass(90)).toBe("E");
    expect(aspectCompass(180)).toBe("S");
    expect(aspectCompass(270)).toBe("W");
    expect(aspectCompass(45)).toBe("NE");
    expect(aspectCompass(360)).toBe("N");
    expect(aspectCompass(338)).toBe("N");
  });
});

describe("slopeBucketLabel", () => {
  it("maps band boundaries (en-dash labels)", () => {
    expect(slopeBucketLabel(14.9)).toBe("0–15°");
    expect(slopeBucketLabel(15)).toBe("15–25°");
    expect(slopeBucketLabel(32)).toBe("30–35°");
    expect(slopeBucketLabel(40)).toBe("35–45°");
    expect(slopeBucketLabel(45)).toBe("45°+");
    expect(slopeBucketLabel(60)).toBe("45°+");
  });
});
