import { describe, it, expect } from "vitest";
import { SLOPE_BUCKETS, ASPECT_COLORS, slopeColor, aspectColor } from "./terrainColors";

describe("slope buckets", () => {
  it("has the six avalanche buckets", () => {
    expect(SLOPE_BUCKETS.map((b) => b.label)).toEqual(
      ["0–15°", "15–25°", "25–30°", "30–35°", "35–45°", "45°+"],
    );
  });
  it("maps a degree to the right bucket color", () => {
    expect(slopeColor(5)).toBe("#1a9850");
    expect(slopeColor(40)).toBe("#d73027");
    expect(slopeColor(60)).toBe("#7b3294");
  });
});

describe("aspect colors", () => {
  it("has 8 directions", () => {
    expect(Object.keys(ASPECT_COLORS)).toHaveLength(8);
  });
  it("maps degrees to the nearest direction color", () => {
    expect(aspectColor(0)).toBe(ASPECT_COLORS.N);
    expect(aspectColor(90)).toBe(ASPECT_COLORS.E);
    expect(aspectColor(225)).toBe(ASPECT_COLORS.SW);
  });
});
