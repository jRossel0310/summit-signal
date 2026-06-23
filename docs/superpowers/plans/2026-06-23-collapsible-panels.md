# Collapsible Side Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user collapse/expand the left (Plan) and right (info) side panels independently — with persistence and a smooth animated slide — so the map gets more room.

**Architecture:** A pure `panelLayout` helper module (class-name + localStorage) drives a `usePanelCollapse` hook; App applies collapse classes to `.dashboard`, renders a collapse button inside each panel and a reopen tab on the map edge; CSS animates the grid track to zero per breakpoint; MapView observes its container and calls `map.resize()` so the canvas fills the reclaimed space.

**Tech Stack:** Vite + React + TypeScript, MapLibre GL, vitest. No new dependencies.

## Global Constraints

- No new dependencies (npm).
- Independent collapse for left and right; state persists in `localStorage` keys `summitsignal_panel_left` / `summitsignal_panel_right`.
- Scope: tablet (≥700px) and desktop (≥1100px). Phone (<700px, bottom sheet) is untouched.
- Do not change panel *contents* (PlanPanel/TripForm/ConditionDashboard/PointDashboard), the map, layers, or the phone bottom sheet.
- Backend untouched.

---

## Task 1: Pure layout helpers (`panelLayout.ts`)

**Files:**
- Create: `frontend/src/lib/panelLayout.ts`
- Test: `frontend/src/lib/panelLayout.test.ts`

**Interfaces:**
- Produces: `dashboardClasses(leftCollapsed: boolean, rightCollapsed: boolean): string`; `readPanelCollapsed(side: "left" | "right"): boolean`; `writePanelCollapsed(side: "left" | "right", value: boolean): void`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/panelLayout.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run src/lib/panelLayout.test.ts 2>&1 | tail -12`
Expected: FAIL — `Failed to resolve import "./panelLayout"` / module not found.

- [ ] **Step 3: Implement `panelLayout.ts`**

Create `frontend/src/lib/panelLayout.ts`:

```typescript
// Pure helpers for the collapsible dashboard panels: the wrapper class names and
// localStorage persistence. Storage access is guarded so private mode / disabled
// storage degrades to "not collapsed" instead of throwing.

const KEYS = {
  left: "summitsignal_panel_left",
  right: "summitsignal_panel_right",
} as const;

export function dashboardClasses(leftCollapsed: boolean, rightCollapsed: boolean): string {
  let cls = "dashboard";
  if (leftCollapsed) cls += " is-left-collapsed";
  if (rightCollapsed) cls += " is-right-collapsed";
  return cls;
}

export function readPanelCollapsed(side: "left" | "right"): boolean {
  try {
    return localStorage.getItem(KEYS[side]) === "1";
  } catch {
    return false;
  }
}

export function writePanelCollapsed(side: "left" | "right", value: boolean): void {
  try {
    localStorage.setItem(KEYS[side], value ? "1" : "0");
  } catch {
    /* storage unavailable — ignore */
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run src/lib/panelLayout.test.ts 2>&1 | tail -8`
Expected: all (7) pass.

- [ ] **Step 5: Type-check**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/panelLayout.ts frontend/src/lib/panelLayout.test.ts
git commit -m "feat(collapsible-panels): pure layout class + persistence helpers"
```

---

## Task 2: Hook + App wiring + CSS

**Files:**
- Create: `frontend/src/hooks/usePanelCollapse.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: `dashboardClasses`, `readPanelCollapsed`, `writePanelCollapsed` from `../lib/panelLayout`.
- Produces: `usePanelCollapse(): { leftCollapsed: boolean; rightCollapsed: boolean; toggleLeft: () => void; toggleRight: () => void }`.

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/usePanelCollapse.ts`:

```typescript
import { useEffect, useState } from "react";
import { readPanelCollapsed, writePanelCollapsed } from "../lib/panelLayout";

export interface PanelCollapseState {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  toggleLeft: () => void;
  toggleRight: () => void;
}

export function usePanelCollapse(): PanelCollapseState {
  const [leftCollapsed, setLeft] = useState(() => readPanelCollapsed("left"));
  const [rightCollapsed, setRight] = useState(() => readPanelCollapsed("right"));

  useEffect(() => { writePanelCollapsed("left", leftCollapsed); }, [leftCollapsed]);
  useEffect(() => { writePanelCollapsed("right", rightCollapsed); }, [rightCollapsed]);

  return {
    leftCollapsed,
    rightCollapsed,
    toggleLeft: () => setLeft((v) => !v),
    toggleRight: () => setRight((v) => !v),
  };
}
```

- [ ] **Step 2: Wire into `App.tsx` — imports + hook**

In `frontend/src/App.tsx`, add imports near the other hook/lib imports (e.g. after `import { useIsPhone } from "./lib/useIsPhone";`):

```typescript
import { usePanelCollapse } from "./hooks/usePanelCollapse";
import { dashboardClasses } from "./lib/panelLayout";
```

Inside `App()`, right after `const rb = useRouteBuilder();`, add:

```typescript
  const panels = usePanelCollapse();
```

- [ ] **Step 3: App — dashboard class + collapse buttons + reopen tabs**

(a) Change the dashboard wrapper. Find `{view === "dashboard" && (` followed by `<div className="dashboard">` and replace that opening div with:

```typescript
        <div className={dashboardClasses(panels.leftCollapsed, panels.rightCollapsed)}>
```

(b) Add a collapse button as the FIRST child of the left aside. Find:

```typescript
            <aside className="panel-left contour-bg">
              <PlanPanel
```

and insert the button:

```typescript
            <aside className="panel-left contour-bg">
              <button
                className="panel-collapse-btn left"
                aria-label="Collapse plan panel"
                onClick={panels.toggleLeft}
              />
              <PlanPanel
```

(c) Add a collapse button as the FIRST child of the right aside. Find:

```typescript
          {!isPhone && (
            <aside className="panel-right">
              <div className="section">
                <h2 className="section-title">This point</h2>
```

and insert the button right after the `<aside className="panel-right">` line:

```typescript
          {!isPhone && (
            <aside className="panel-right">
              <button
                className="panel-collapse-btn right"
                aria-label="Collapse info panel"
                onClick={panels.toggleRight}
              />
              <div className="section">
                <h2 className="section-title">This point</h2>
```

(d) Add the two reopen tabs inside `.panel-center`, immediately AFTER the RouteBuilder overlay block (the `{user && ( <div className="map-overlay-rb"> ... </div> )}`) and BEFORE the closing `</main>`:

```typescript
            {!isPhone && panels.leftCollapsed && (
              <button
                className="panel-reopen-tab left"
                aria-label="Open plan panel"
                onClick={panels.toggleLeft}
              >
                Plan
              </button>
            )}
            {!isPhone && panels.rightCollapsed && (
              <button
                className="panel-reopen-tab right"
                aria-label="Open info panel"
                onClick={panels.toggleRight}
              >
                Info
              </button>
            )}
```

(`isPhone` already exists in `App()` via `const isPhone = useIsPhone();`.)

- [ ] **Step 4: CSS — animation, collapse grid states, button/tab styles**

Append to the END of `frontend/src/index.css`:

```css
/* ---------- Collapsible side panels ---------- */
.dashboard { transition: grid-template-columns 0.28s ease, grid-template-rows 0.28s ease; }

/* Edge controls (shared). Reopen tabs are hidden until >=700 (and only render
   when a panel is collapsed). Collapse buttons live inside the panels, so they
   are naturally hidden on phone where the panels are display:none. */
.panel-collapse-btn,
.panel-reopen-tab {
  position: absolute;
  z-index: 6;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--panel, #fbfaf6);
  color: var(--ink-soft, #6b6456);
  border: 1px solid var(--line-strong, #d8d2c4);
  cursor: pointer;
  padding: 0;
  font-family: var(--mono, monospace);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  line-height: 1;
}
.panel-collapse-btn { font-size: 15px; }
.panel-collapse-btn:hover,
.panel-reopen-tab:hover { color: var(--ink, #1f241f); }
.panel-collapse-btn::after { content: "\2039"; }        /* ‹ for the left panel */
.panel-collapse-btn.right::after { content: "\203A"; }  /* › for the right panel */
.panel-reopen-tab { display: none; }

@media (min-width: 700px) {
  /* collapsed grid tracks (tablet 2-col; right panel is a bottom strip) */
  .dashboard.is-left-collapsed { grid-template-columns: 0 1fr; }
  .dashboard.is-right-collapsed { grid-template-rows: 1fr 0; }
  .dashboard.is-left-collapsed.is-right-collapsed {
    grid-template-columns: 0 1fr; grid-template-rows: 1fr 0;
  }

  /* anchor + clean horizontal clip while the track animates to 0 */
  .dashboard .panel-left,
  .dashboard .panel-right { position: relative; overflow: hidden auto; }

  /* collapse buttons sit on each panel's inner edge, vertically centered */
  .panel-collapse-btn.left {
    top: 50%; right: 0; transform: translateY(-50%);
    width: 16px; height: 48px; border-radius: 4px 0 0 4px;
  }
  .panel-collapse-btn.right {
    top: 50%; left: 0; transform: translateY(-50%);
    width: 16px; height: 48px; border-radius: 0 4px 4px 0;
  }

  /* reopen tabs: slim vertical tabs on the map edge */
  .panel-reopen-tab {
    display: inline-flex;
    top: 50%; transform: translateY(-50%);
    width: 24px; height: 88px; padding: 10px 0;
    writing-mode: vertical-rl;
  }
  .panel-reopen-tab.left { left: 0; border-radius: 0 6px 6px 0; }
  .panel-reopen-tab.right { right: 0; border-radius: 6px 0 0 6px; }
}

/* tablet only: the right panel is a bottom strip, so its controls live on the
   horizontal (top/bottom) edges instead of the vertical edges */
@media (min-width: 700px) and (max-width: 1099px) {
  .panel-collapse-btn.right {
    top: 0; left: 50%; right: auto; transform: translateX(-50%);
    width: 48px; height: 16px; border-radius: 0 0 4px 4px;
  }
  .panel-collapse-btn.right::after { content: "\2304"; }   /* ⌄ */
  .panel-reopen-tab.right {
    top: auto; bottom: 0; right: 50%; left: auto; transform: translateX(50%);
    width: 96px; height: 22px; padding: 0 10px; writing-mode: horizontal-tb;
    border-radius: 6px 6px 0 0;
  }
}

@media (min-width: 1100px) {
  /* desktop 3-col: both panels are side columns; reset any tablet row collapse */
  .dashboard.is-left-collapsed { grid-template-columns: 0 1fr 430px; grid-template-rows: none; }
  .dashboard.is-right-collapsed { grid-template-columns: 330px 1fr 0; grid-template-rows: none; }
  .dashboard.is-left-collapsed.is-right-collapsed {
    grid-template-columns: 0 1fr 0; grid-template-rows: none;
  }
}
```

- [ ] **Step 5: Type-check and build**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3`
Expected: tsc clean; build succeeds.

- [ ] **Step 6: Run the test suite (no regression)**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run 2>&1 | tail -5`
Expected: all pass (existing + Task 1 helpers).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/usePanelCollapse.ts frontend/src/App.tsx frontend/src/index.css
git commit -m "feat(collapsible-panels): hook, panel toggles/tabs, animated grid CSS"
```

---

## Task 3: Map fills reclaimed space (`MapView` ResizeObserver)

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

**Interfaces:**
- Consumes: the existing `containerRef` and `mapRef` in `MapView`.
- Produces: nothing external; the map canvas resizes when its container changes size.

- [ ] **Step 1: Add a ResizeObserver in the init effect**

In `frontend/src/components/MapView.tsx`, inside the one-time init `useEffect` (the one that does `const map = new maplibregl.Map({...})` and `mapRef.current = map;`), add a ResizeObserver right AFTER `mapRef.current = map;`:

```typescript
    let resizeObs: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      resizeObs = new ResizeObserver(() => { mapRef.current?.resize(); });
      resizeObs.observe(containerRef.current);
    }
```

- [ ] **Step 2: Disconnect it in the cleanup**

In the same effect's cleanup `return () => { ... }`, add `resizeObs?.disconnect();` as the FIRST line of the cleanup (before the existing waypoint-marker cleanup / `map.remove()`):

```typescript
    return () => {
      resizeObs?.disconnect();
      for (const m of wpMarkersRef.current) m.remove();
      wpMarkersRef.current = [];
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
```

(If the current cleanup differs slightly, keep its existing lines and just add `resizeObs?.disconnect();` as the first statement.)

- [ ] **Step 3: Type-check and build**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3`
Expected: tsc clean; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "feat(collapsible-panels): resize map canvas when its container changes size"
```

---

## Task 4: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Frontend checks**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3 && npx vitest run 2>&1 | tail -5`
Expected: tsc clean; build succeeds; all vitest pass.

- [ ] **Step 2: Manual smoke (optional, requires running the app)**

On a desktop-width window, logged in:
1. Click the ‹ on the left panel → it slides closed, the map widens, a vertical "Plan" tab appears on the map's left edge.
2. Click the "Plan" tab → the panel slides back.
3. Same for the right ›/"Info".
4. Reload the page → collapsed panels stay collapsed (persistence).
5. Narrow the window to tablet width → the right (now bottom) panel collapses downward via the ⌄ control and reopens from a bottom "Info" tab; the map fills the space.
6. Narrow to phone width → the bottom sheet behaves exactly as before; no panel tabs appear.

- [ ] **Step 3: Final commit (only if verification fixes were needed)**

```bash
git add -A
git commit -m "test(collapsible-panels): verification pass"
```

---

## Self-Review Notes (author)

- **Spec coverage:** helpers (class + persistence) → Task 1; hook + App wiring (dashboard class, collapse buttons, reopen tabs) → Task 2; animated grid collapse for tablet (right = bottom-row vertical collapse) and desktop (right = column horizontal collapse) → Task 2 CSS; map fills space → Task 3; tests → Tasks 1 + 4; phone untouched (controls gated `!isPhone`, reopen tabs `display:none` until ≥700, panels already `display:none` on phone).
- **No placeholders:** complete code for helpers, hook, App edits, full CSS, and MapView changes.
- **Type consistency:** `usePanelCollapse` returns `{leftCollapsed,rightCollapsed,toggleLeft,toggleRight}` exactly as used in App; `dashboardClasses(left,right)` signature matches its call; class names `is-left-collapsed`/`is-right-collapsed` match between helper output and CSS selectors; control class names (`panel-collapse-btn`/`panel-reopen-tab`, `.left`/`.right`) match between JSX and CSS.
- **Isolation:** collapse logic lives in `panelLayout` + `usePanelCollapse`; MapView change is a self-contained ResizeObserver; panel contents unchanged.
```
