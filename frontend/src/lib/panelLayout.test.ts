import { describe, it, expect, afterEach, vi } from "vitest";
import { dashboardClasses, readPanelCollapsed, writePanelCollapsed } from "./panelLayout";

function makeStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? (m.get(k) as string) : null),
    setItem: (k: string, v: string) => { m.set(k, v); },
    removeItem: (k: string) => { m.delete(k); },
    clear: () => m.clear(),
  };
}

describe("dashboardClasses", () => {
  it("base class when nothing collapsed", () => {
    expect(dashboardClasses(false, false)).toBe("dashboard");
  });
  it("adds left", () => {
    expect(dashboardClasses(true, false)).toBe("dashboard is-left-collapsed");
  });
  it("adds right", () => {
    expect(dashboardClasses(false, true)).toBe("dashboard is-right-collapsed");
  });
  it("adds both", () => {
    expect(dashboardClasses(true, true)).toBe("dashboard is-left-collapsed is-right-collapsed");
  });
});

describe("panel collapse persistence", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("defaults to false when unset", () => {
    vi.stubGlobal("localStorage", makeStorage());
    expect(readPanelCollapsed("left")).toBe(false);
    expect(readPanelCollapsed("right")).toBe(false);
  });
  it("round-trips a written value", () => {
    vi.stubGlobal("localStorage", makeStorage());
    writePanelCollapsed("left", true);
    expect(readPanelCollapsed("left")).toBe(true);
    writePanelCollapsed("left", false);
    expect(readPanelCollapsed("left")).toBe(false);
  });
  it("returns false when localStorage throws", () => {
    vi.stubGlobal("localStorage", { getItem: () => { throw new Error("denied"); }, setItem: () => {} });
    expect(readPanelCollapsed("right")).toBe(false);
  });
});
