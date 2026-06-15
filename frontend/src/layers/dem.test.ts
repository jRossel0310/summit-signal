import { describe, it, expect } from "vitest";
import { getDemSource } from "./dem";

describe("getDemSource", () => {
  it("defaults to free Terrarium with no key", () => {
    const dem = getDemSource();
    expect(dem.encoding).toBe("terrarium");
    expect(dem.tiles[0]).toContain("elevation-tiles-prod");
    expect(dem.maxzoom).toBe(15);
    expect(dem.tileSize).toBe(256);
  });
});
