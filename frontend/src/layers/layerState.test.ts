import { describe, it, expect } from "vitest";
import { seedLayerState, setVisible, enabledDataProviderIds } from "./layerState";

describe("snow is opt-in (layer-gated)", () => {
  it("is not requested by default, and is requested once toggled on", () => {
    const seeded = seedLayerState();
    expect(enabledDataProviderIds(seeded)).not.toContain("snow");
    const withSnow = setVisible(seeded, "overlay.snow", true);
    expect(enabledDataProviderIds(withSnow)).toContain("snow");
  });
});
