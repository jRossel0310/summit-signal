import { describe, it, expect } from "vitest";
import { OVERLAY_LAYERS } from "./registry";

describe("overlay layer descriptions", () => {
  it("every overlay has a non-empty description", () => {
    const missing = OVERLAY_LAYERS.filter((l) => !l.description || !l.description.trim());
    expect(missing.map((l) => l.id)).toEqual([]);
  });
});

describe("3D terrain overlay", () => {
  it("exists in the terrain group with the terrain-3d kind", () => {
    const t = OVERLAY_LAYERS.find((l) => l.id === "overlay.terrain3d");
    expect(t).toBeTruthy();
    expect(t?.group).toBe("terrain");
    expect(t?.kind).toBe("terrain-3d");
    expect(t?.description && t.description.trim().length).toBeTruthy();
  });
});
