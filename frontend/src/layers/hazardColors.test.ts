import { describe, it, expect } from "vitest";
import { aqiColor, aqiCategory, avyColor } from "./hazardColors";

describe("aqi", () => {
  it("colors by EPA breakpoint", () => {
    expect(aqiColor(40)).toBe("#00e400");   // good
    expect(aqiColor(120)).toBe("#ff7e00");  // USG
    expect(aqiColor(250)).toBe("#8f3f97");  // very unhealthy
  });
  it("labels categories", () => {
    expect(aqiCategory(40)).toBe("Good");
    expect(aqiCategory(160)).toBe("Unhealthy");
  });
});

describe("avalanche danger", () => {
  it("colors by NAC level (name or number)", () => {
    expect(avyColor("Considerable")).toBe("#f7941e");
    expect(avyColor("High")).toBe("#ed1c24");
    expect(avyColor(1)).toBe("#52ba4a"); // Low
  });
});
