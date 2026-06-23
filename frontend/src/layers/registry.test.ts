import { describe, it, expect } from "vitest";
import { OVERLAY_LAYERS } from "./registry";

describe("overlay layer descriptions", () => {
  it("every overlay has a non-empty description", () => {
    const missing = OVERLAY_LAYERS.filter((l) => !l.description || !l.description.trim());
    expect(missing.map((l) => l.id)).toEqual([]);
  });
});
