# Mobile-First Responsive Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SummitSignal usable and polished on phone (360–430px), tablet, and desktop by making the map the primary mobile surface with a draggable bottom sheet, while preserving the desktop 3-column layout. Frontend only; no backend/API changes.

**Architecture:** Mobile-first CSS (base = phone, `min-width` queries scale up). On phone, a permanently-mounted full-screen `MapView` sits under one draggable `BottomSheet` with peek/half/full snap points; the peek always shows the selected trip + color-coded risk + Run-check. A `useIsPhone()` hook swaps between the sheet (phone) and the existing grid side-panels (tablet/desktop) without remounting the map. Plan content is extracted into a reusable `PlanPanel` so it renders identically in the desktop left panel and the phone sheet.

**Tech Stack:** Vite + React 18 + TypeScript, MapLibre GL, plain CSS (no UI/animation libraries). Pointer Events for the drag gesture.

**Testing note (read first):** This project has **no test runner** (see `frontend/package.json`) and the work is visual/layout. Per the approved spec, per-task verification is **`npm run build` (tsc typecheck + vite build) passing** plus **visual confirmation**, not unit tests. We do not add a test framework for a CSS/responsive redesign. The final task adds best-effort Playwright screenshots at 375/768/1280px.

**Prerequisites:** Frontend dependencies may not be installed (they were recently untracked). Before Task 1, run once:

```bash
cd frontend && npm install
```

Expected: `node_modules/` populated, no errors.

---

## File Structure

**Create:**
- `frontend/src/lib/useIsPhone.ts` — `matchMedia('(max-width: 699px)')` hook. Drives the render split.
- `frontend/src/components/BottomSheet.tsx` — generic draggable snap sheet (peek/half/full). Owns drag math; phone-only (rendered conditionally by App).
- `frontend/src/components/PlanPanel.tsx` — extracted "New trip + Saved trips + Map layers" content, reused by desktop left panel and phone sheet.

**Modify:**
- `frontend/src/App.tsx` — extract `PlanPanel`; add `SheetPeek` + `LoggedOutConditions` inline helpers; render sheet (phone) vs panels (tablet/desktop); remove the old bottom-tabbar / `compactPanel` mechanism and the `MapIcon`/`PlanIcon`/`ConditionsIcon` glyphs.
- `frontend/src/index.css` — invert layout section to mobile-first; add bottom-sheet + peek + segmented styles; dashboard readability (`.kv` stacking, action stacking); component touch/breakpoint alignment; visual-elevation polish.
- `frontend/src/components/ConditionDashboard.tsx` — replace the inline action-row style with `.dash-actions` class.
- `frontend/src/components/TripForm.tsx` — add `elevation` class to the elevation `field-row` (wrap-safe).
- `frontend/src/components/AuthScreen.tsx` — replace fixed `8vh` inline margin with the `.auth-screen` class.
- `frontend/index.html` — already carries `viewport-fit=cover` + `theme-color`; no change required (verify only).

---

## Task 1: `useIsPhone` hook

**Files:**
- Create: `frontend/src/lib/useIsPhone.ts`

- [ ] **Step 1: Create the hook**

```ts
import { useEffect, useState } from "react";

// True when the viewport is phone-width (<=699px). Drives the bottom-sheet vs
// side-panel render split without remounting the (expensive) MapLibre map.
const QUERY = "(max-width: 699px)";

export function useIsPhone(): boolean {
  const [isPhone, setIsPhone] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches,
  );

  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setIsPhone(e.matches);
    mq.addEventListener("change", onChange);
    setIsPhone(mq.matches); // sync in case it changed before the listener attached
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return isPhone;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: no errors (the file is unused for now, but must compile).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/useIsPhone.ts
git commit -m "feat(frontend): add useIsPhone media-query hook"
```

---

## Task 2: Extract `PlanPanel` (no behavior change)

Move the "New trip + Saved trips + Map layers" block out of `App.tsx` into a reusable component, then render it in the existing left panel. Desktop output must be identical.

**Files:**
- Create: `frontend/src/components/PlanPanel.tsx`
- Modify: `frontend/src/App.tsx` (left panel body, lines ~341-398)

- [ ] **Step 1: Create `PlanPanel.tsx`**

```tsx
import type { Trip } from "../types";
import type { LayerState } from "./MapView";
import TripForm from "./TripForm";
import SavedTrips from "./SavedTrips";

interface Props {
  loggedIn: boolean;
  selectedPoint: { lat: number; lon: number } | null;
  pointName: string | null;
  trips: Trip[];
  selectedTripId: number | null;
  layers: LayerState;
  runningAll: boolean;
  onTripCreated: (trip: Trip) => void;
  onSelectTrip: (trip: Trip) => void;
  onOpenDetail: (trip: Trip) => void;
  onRunAll: () => void;
  onLayersChange: (layers: LayerState) => void;
  onLoginClick: () => void;
}

const LAYER_ROWS: [keyof LayerState, string][] = [
  ["selectedPoint", "Selected trip point"],
  ["gpxRoute", "GPX route"],
  ["fires", "Active fire detections"],
  ["perimeters", "Fire perimeters"],
  ["savedTrips", "Saved trip markers"],
];

export default function PlanPanel({
  loggedIn, selectedPoint, pointName, trips, selectedTripId, layers, runningAll,
  onTripCreated, onSelectTrip, onOpenDetail, onRunAll, onLayersChange, onLoginClick,
}: Props) {
  return (
    <>
      {loggedIn ? (
        <>
          <div className="section">
            <h2 className="section-title">New trip</h2>
            <TripForm selectedPoint={selectedPoint} locationName={pointName} onCreated={onTripCreated} />
          </div>
          <div className="section">
            <h2 className="section-title">Saved trips ({trips.length})</h2>
            <SavedTrips
              trips={trips}
              selectedTripId={selectedTripId}
              onSelect={onSelectTrip}
              onOpenDetail={onOpenDetail}
              onRunAll={onRunAll}
              runningAll={runningAll}
            />
          </div>
        </>
      ) : (
        <div className="section">
          <div className="empty-note">
            Log in to save trips and run condition checks. You can browse and search the map without an account.
          </div>
          <button className="btn primary" style={{ marginTop: 8 }} onClick={onLoginClick}>Log in / Sign up</button>
        </div>
      )}

      <div className="section">
        <h2 className="section-title">Map layers</h2>
        <div className="layer-toggles">
          <label>
            <input
              type="checkbox"
              checked={layers.basemap === "topo"}
              onChange={(e) => onLayersChange({ ...layers, basemap: e.target.checked ? "topo" : "street" })}
            />
            Topo basemap (off = street)
          </label>
          {LAYER_ROWS.map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={layers[key] as boolean}
                onChange={(e) => onLayersChange({ ...layers, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="layer-note">
          Fire detections and perimeters appear after a condition check returns data for the selected trip.
          AQI, NWS alert areas, and avalanche regions are shown in the conditions panel with source links.
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Use it in `App.tsx`'s left panel.** Replace the entire body of `<aside className="panel-left contour-bg"> … </aside>` (the `sheet-grip` button + the `user ? (...) : (...)` block + the Map-layers `<div className="section">`) with:

```tsx
<aside className="panel-left contour-bg">
  <PlanPanel
    loggedIn={!!user}
    selectedPoint={selectedPoint}
    pointName={pointName}
    trips={trips}
    selectedTripId={selectedTrip?.id ?? null}
    layers={layers}
    runningAll={runningAll}
    onTripCreated={onTripCreated}
    onSelectTrip={selectTrip}
    onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
    onRunAll={runAll}
    onLayersChange={setLayers}
    onLoginClick={() => setView("auth")}
  />
</aside>
```

Add the import at the top of `App.tsx` (near the other component imports):

```tsx
import PlanPanel from "./components/PlanPanel";
```

(The `sheet-grip` button inside `panel-left` is intentionally dropped — the sheet model in Task 4 replaces it. The inline `style={{ fontSize: 11, ... }}` layer note becomes the `.layer-note` class, styled in Task 5.)

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: builds; desktop left panel unchanged visually.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PlanPanel.tsx frontend/src/App.tsx
git commit -m "refactor(frontend): extract PlanPanel from App left panel"
```

---

## Task 3: `BottomSheet` component

Generic draggable sheet with peek/half/full snap points. Standalone and unused after this task (wired in Task 4); must compile.

**Files:**
- Create: `frontend/src/components/BottomSheet.tsx`

- [ ] **Step 1: Create `BottomSheet.tsx`**

```tsx
import { useLayoutEffect, useRef, type PointerEvent, type ReactNode } from "react";

export type SheetSnap = "peek" | "half" | "full";
const ORDER: SheetSnap[] = ["peek", "half", "full"];
const TAP_THRESHOLD_PX = 5;

interface Props {
  snap: SheetSnap;
  onSnapChange: (s: SheetSnap) => void;
  peek: ReactNode;     // always-visible header (trip + risk + action)
  children: ReactNode; // expanded content (segmented control + active panel)
  ariaLabel?: string;
}

// Read the rendered translateY (px) from the computed transform matrix. Works
// whether the value came from the data-snap CSS rule (%) or an inline px drag.
function getTranslateY(el: HTMLElement): number {
  const t = getComputedStyle(el).transform;
  if (!t || t === "none") return 0;
  const m3 = t.match(/matrix3d\((.+)\)/);
  if (m3) return parseFloat(m3[1].split(",")[13]);
  const m = t.match(/matrix\((.+)\)/);
  if (m) return parseFloat(m[1].split(",")[5]);
  return 0;
}

function peekHeight(el: HTMLElement): number {
  const grip = el.querySelector<HTMLElement>(".sheet-grip");
  const peek = el.querySelector<HTMLElement>(".sheet-peek");
  return (grip?.offsetHeight ?? 0) + (peek?.offsetHeight ?? 0) || 156;
}

export default function BottomSheet({ snap, onSnapChange, peek, children, ariaLabel = "Trip panel" }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ startY: number; start: number; max: number; sheetH: number; moved: boolean } | null>(null);

  // Keep the CSS peek height in sync with the actual grip + peek content so the
  // peek resting position never clips the risk banner or leaks the body.
  useLayoutEffect(() => {
    const el = sheetRef.current;
    if (!el) return;
    el.style.setProperty("--sheet-peek", `${peekHeight(el)}px`);
  });

  function onPointerDown(e: PointerEvent) {
    const el = sheetRef.current;
    if (!el) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    const sheetH = el.offsetHeight;
    drag.current = {
      startY: e.clientY,
      start: getTranslateY(el),
      max: sheetH - peekHeight(el),
      sheetH,
      moved: false,
    };
    el.dataset.dragging = "true";
  }

  function onPointerMove(e: PointerEvent) {
    const el = sheetRef.current;
    const d = drag.current;
    if (!el || !d) return;
    const dy = e.clientY - d.startY;
    if (Math.abs(dy) > TAP_THRESHOLD_PX) d.moved = true;
    const next = Math.min(Math.max(d.start + dy, 0), d.max);
    el.style.setProperty("--sheet-translate", `${next}px`);
  }

  function onPointerUp() {
    const el = sheetRef.current;
    const d = drag.current;
    if (!el || !d) return;
    el.dataset.dragging = "false";
    drag.current = null;

    if (!d.moved) {
      // Treat as a tap on the grip: cycle upward.
      const i = ORDER.indexOf(snap);
      el.style.removeProperty("--sheet-translate");
      onSnapChange(ORDER[Math.min(i + 1, ORDER.length - 1)]);
      return;
    }

    const current = getTranslateY(el);
    const targets: Record<SheetSnap, number> = { full: 0, half: d.sheetH * 0.45, peek: d.max };
    let best: SheetSnap = "peek";
    let bestDist = Infinity;
    (Object.keys(targets) as SheetSnap[]).forEach((k) => {
      const dist = Math.abs(targets[k] - current);
      if (dist < bestDist) { bestDist = dist; best = k; }
    });
    el.style.removeProperty("--sheet-translate"); // let the data-snap CSS animate to rest
    onSnapChange(best);
  }

  return (
    <div ref={sheetRef} className="bottom-sheet" data-snap={snap} role="dialog" aria-label={ariaLabel} aria-modal="false">
      <button
        type="button"
        className="sheet-grip"
        aria-label={snap === "full" ? "Collapse panel" : "Expand panel"}
        aria-expanded={snap !== "peek"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="grip-bar" />
      </button>
      <div className="sheet-peek">{peek}</div>
      <div className="sheet-body">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BottomSheet.tsx
git commit -m "feat(frontend): add draggable BottomSheet with peek/half/full snaps"
```

---

## Task 4: Wire phone sheet into `App.tsx`; remove old tab model

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update imports and types.** At the top of `App.tsx`:
  - Add: `import BottomSheet, { type SheetSnap } from "./components/BottomSheet";`
  - Add: `import { useIsPhone } from "./lib/useIsPhone";`
  - (PlanPanel import already added in Task 2.)
  - **Delete** the `type CompactPanel = ...` line.
  - **Delete** the `MapIcon`, `PlanIcon`, and `ConditionsIcon` component definitions (only the tabbar used them). **Keep** `Logo` and `concernColor`.

- [ ] **Step 2: Update state.** In `App()`:
  - **Delete:** `const [compactPanel, setCompactPanel] = useState<CompactPanel>("map");`
  - **Add:**
    ```tsx
    const isPhone = useIsPhone();
    const [sheetSnap, setSheetSnap] = useState<SheetSnap>("peek");
    const [mobileTab, setMobileTab] = useState<"conditions" | "plan">("plan");
    ```

- [ ] **Step 3: Update `selectTrip`.** Replace the line `setCompactPanel("conditions"); // surface conditions on phone; no-op visually on desktop` with:

```tsx
    setMobileTab("conditions");           // surface conditions on phone
    setSheetSnap((s) => (s === "peek" ? "half" : s));
```

- [ ] **Step 4: Add inline helper components** just above `export default function App()` (after `concernColor`):

```tsx
function LoggedOutConditions({ onLogin }: { onLogin: () => void }) {
  return (
    <div className="section">
      <h2 className="section-title">Condition dashboard</h2>
      <div className="empty-note">Log in to run condition checks and see source results for your trips.</div>
      <button className="btn primary" style={{ marginTop: 8 }} onClick={onLogin}>Log in / Sign up</button>
    </div>
  );
}

function SheetPeek({
  loggedIn, trip, check, running, liveStatus, onRunCheck, onLogin,
}: {
  loggedIn: boolean;
  trip: Trip | null;
  check: ConditionCheckDetail | null;
  running: boolean;
  liveStatus: CheckStatus | null;
  onRunCheck: () => void;
  onLogin: () => void;
}) {
  if (!loggedIn) {
    return (
      <div className="peek-empty">
        <div className="peek-title">Browse the map</div>
        <div className="peek-sub">Log in to save trips and run condition checks.</div>
        <button className="btn primary small peek-run" onClick={onLogin}>Log in / Sign up</button>
      </div>
    );
  }
  if (!trip) {
    return (
      <div className="peek-empty">
        <div className="peek-title">No trip selected</div>
        <div className="peek-sub">Search or tap the map, then save a trip in the Plan tab.</div>
      </div>
    );
  }
  const status = running ? "Check in progress" : (check?.overall_concern_status ?? trip.latest_concern_status);
  const dotColor = running ? "var(--accent)" : concernColor(check?.overall_concern_status ?? trip.latest_concern_status);
  return (
    <div className="peek">
      <div className="peek-trip">{trip.name}</div>
      <div className="peek-risk">
        <span className="peek-dot" style={{ background: dotColor }} />
        <span className="peek-status">{status ?? "Not yet checked"}</span>
      </div>
      {running && liveStatus ? (
        <div className="peek-progress">{liveStatus.connectors_completed}/{liveStatus.connectors_total} sources checked…</div>
      ) : (
        <button className="btn primary peek-run" onClick={onRunCheck} disabled={running}>Run condition check</button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Replace the dashboard render block.** Replace the entire `{view === "dashboard" && ( <> … </> )}` block (the `.main-grid` + `.mobile-tabbar`) with:

```tsx
      {view === "dashboard" && (
        <div className="dashboard">
          {!isPhone && (
            <aside className="panel-left contour-bg">
              <PlanPanel
                loggedIn={!!user}
                selectedPoint={selectedPoint}
                pointName={pointName}
                trips={trips}
                selectedTripId={selectedTrip?.id ?? null}
                layers={layers}
                runningAll={runningAll}
                onTripCreated={onTripCreated}
                onSelectTrip={selectTrip}
                onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
                onRunAll={runAll}
                onLayersChange={setLayers}
                onLoginClick={() => setView("auth")}
              />
            </aside>
          )}

          <main className="panel-center">
            <MapView
              layers={layers}
              trips={trips}
              selectedTripId={selectedTrip?.id ?? null}
              selectedPoint={selectedPoint}
              flyTo={flyTo}
              gpxPoints={gpxPoints}
              fireDetections={fireDetections}
              perimeterGeojson={perimeterGeojson}
              onSelectPoint={onMapSelect}
              onSelectTrip={(id) => { const t = trips.find((x) => x.id === id); if (t) selectTrip(t); }}
            />
            <div className="map-overlay-tl">
              <SearchBar onResult={onSearchResult} />
            </div>
          </main>

          {!isPhone && (
            <aside className="panel-right">
              {user ? (
                <ConditionDashboard
                  trip={selectedTrip}
                  check={check}
                  liveStatus={liveStatus}
                  running={running}
                  loadingCheck={loadingCheck}
                  error={dashError}
                  staleHours={settings?.stale_hours ?? 24}
                  onRunCheck={runCheck}
                  onRegenerateSummary={regenerateSummary}
                  regenBusy={regenBusy}
                />
              ) : (
                <LoggedOutConditions onLogin={() => setView("auth")} />
              )}
            </aside>
          )}

          {isPhone && (
            <BottomSheet
              snap={sheetSnap}
              onSnapChange={setSheetSnap}
              peek={
                <SheetPeek
                  loggedIn={!!user}
                  trip={selectedTrip}
                  check={check}
                  running={running}
                  liveStatus={liveStatus}
                  onRunCheck={runCheck}
                  onLogin={() => setView("auth")}
                />
              }
            >
              <div className="sheet-segmented" role="tablist" aria-label="Sheet content">
                <button
                  type="button" role="tab" aria-selected={mobileTab === "conditions"}
                  className={mobileTab === "conditions" ? "active" : ""}
                  onClick={() => { setMobileTab("conditions"); setSheetSnap((s) => (s === "peek" ? "half" : s)); }}
                >
                  Conditions
                </button>
                <button
                  type="button" role="tab" aria-selected={mobileTab === "plan"}
                  className={mobileTab === "plan" ? "active" : ""}
                  onClick={() => { setMobileTab("plan"); setSheetSnap((s) => (s === "peek" ? "half" : s)); }}
                >
                  Plan
                </button>
              </div>
              <div className="sheet-tabpanel" role="tabpanel">
                {mobileTab === "conditions" ? (
                  user ? (
                    <ConditionDashboard
                      trip={selectedTrip}
                      check={check}
                      liveStatus={liveStatus}
                      running={running}
                      loadingCheck={loadingCheck}
                      error={dashError}
                      staleHours={settings?.stale_hours ?? 24}
                      onRunCheck={runCheck}
                      onRegenerateSummary={regenerateSummary}
                      regenBusy={regenBusy}
                    />
                  ) : (
                    <LoggedOutConditions onLogin={() => setView("auth")} />
                  )
                ) : (
                  <PlanPanel
                    loggedIn={!!user}
                    selectedPoint={selectedPoint}
                    pointName={pointName}
                    trips={trips}
                    selectedTripId={selectedTrip?.id ?? null}
                    layers={layers}
                    runningAll={runningAll}
                    onTripCreated={onTripCreated}
                    onSelectTrip={selectTrip}
                    onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
                    onRunAll={runAll}
                    onLayersChange={setLayers}
                    onLoginClick={() => setView("auth")}
                  />
                )}
              </div>
            </BottomSheet>
          )}
        </div>
      )}
```

- [ ] **Step 6: Build**

Run: `cd frontend && npm run build`
Expected: builds with no unused-variable or type errors. (If `MapIcon`/`PlanIcon`/`ConditionsIcon` were not fully removed, `tsc` flags them as unused — delete them.)

> Note: the phone layout will look rough until Task 5 adds the mobile-first CSS. That is expected; the build and logic are what matter here.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): render phone bottom sheet vs desktop panels; drop tab bar"
```

---

## Task 5: Mobile-first layout CSS + bottom-sheet styles

Rewrite the layout region of `index.css` to be mobile-first and add the sheet/peek/segmented styles. This replaces the existing **lines 44–221** (from the `/* ---------- App shell ---------- */` comment through the end of the `@media (max-width: 699px)` block).

**Files:**
- Modify: `frontend/src/index.css` (replace lines 44–221)

- [ ] **Step 1: Add layout tokens to `:root`.** Inside the existing `:root { … }` block (after the `--body` font var), add:

```css
  --topbar-h: 50px;
  --sheet-peek: 156px;   /* runtime-overridden by BottomSheet */
```

- [ ] **Step 2: Replace lines 44–221** with the following mobile-first block:

```css
/* ---------- App shell ---------- */
.app-shell { display: flex; flex-direction: column; height: 100vh; height: 100dvh; }

/* Keep long source strings, URLs and values from forcing horizontal scroll. */
.kv .v, .conn-row .meta, .conn-row .body, .conn-row .err, .f-title, .f-desc, .f-src,
.t-meta, .detail-meta, .summary-md, .summary-md a, .status-banner .value,
.search-results .res, .empty-note, .error-note {
  overflow-wrap: anywhere;
}
.kv, .flag-row .f-body, .conn-row, .conn-row .head, .card, .section { min-width: 0; }

/* ---------- Topbar (phone base) ---------- */
.topbar {
  display: flex; align-items: center; gap: 8px;
  padding: 0 12px; height: var(--topbar-h);
  background: var(--ink); color: var(--paper);
  border-bottom: 3px solid var(--accent); flex-shrink: 0;
}
.brand { display: flex; align-items: center; gap: 9px; min-width: 0; flex-shrink: 1; }
.brand svg { display: block; flex-shrink: 0; }
.brand-name {
  font-family: var(--display); font-weight: 700; font-size: 18px;
  letter-spacing: 0.04em; text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.brand-sub { display: none; }
.topbar-nav { margin-left: auto; display: flex; gap: 3px; flex-shrink: 0; }
.topbar-nav button {
  background: transparent; border: 1px solid transparent; color: #cfd5c9;
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em;
  padding: 8px 9px; border-radius: 3px; text-transform: uppercase; min-height: 40px;
}
.topbar-nav button:hover { color: var(--paper); border-color: #4a514a; }
.topbar-nav button.active { color: var(--paper); border-color: var(--accent); background: rgba(216, 74, 27, 0.16); }
.nav-email { display: none; }
.hide-on-mobile { display: none; }

.backend-dot { font-family: var(--mono); font-size: 11px; display: flex; align-items: center; gap: 0; color: #9aa395; }
.backend-host { display: none; }
.backend-dot .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--gray); }
.backend-dot .dot.ok { background: #34d399; }
.backend-dot .dot.bad { background: var(--accent); }

/* ---------- Dashboard (phone base): full-bleed map + bottom sheet ---------- */
.dashboard { position: relative; flex: 1; min-height: 0; }
.dashboard .panel-left, .dashboard .panel-right { display: none; }
.panel-center { position: absolute; inset: 0; min-width: 0; }
.coord-readout { bottom: 30px; font-size: 12px; }
.map-overlay-br { display: none; }            /* "click map" is mouse language */
.map-overlay-tl { max-width: none; width: calc(100% - 20px); }

/* ---------- Bottom sheet (phone) ---------- */
.bottom-sheet {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
  height: calc(100dvh - var(--topbar-h));
  display: flex; flex-direction: column;
  background: var(--panel);
  border-top: 1px solid var(--line-strong);
  border-radius: 16px 16px 0 0;
  box-shadow: 0 -12px 34px rgba(31, 36, 31, 0.30);
  transform: translateY(var(--sheet-translate, calc(100% - var(--sheet-peek))));
  transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
  touch-action: none;
}
.bottom-sheet[data-snap="full"] { --sheet-translate: 0px; }
.bottom-sheet[data-snap="half"] { --sheet-translate: 45%; }
.bottom-sheet[data-snap="peek"] { --sheet-translate: calc(100% - var(--sheet-peek)); }
.bottom-sheet[data-dragging="true"] { transition: none; }

.sheet-grip {
  flex: 0 0 auto; position: relative; width: 100%;
  padding: 14px 0 8px; background: transparent; border: none; cursor: grab; touch-action: none;
}
.sheet-grip .grip-bar { display: block; margin: 0 auto; width: 42px; height: 4px; border-radius: 2px; background: var(--line-strong); }
.sheet-peek { flex: 0 0 auto; padding: 0 16px 12px; border-bottom: 1px solid var(--line); }
.sheet-body {
  flex: 1 1 auto; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
}

.sheet-segmented {
  position: sticky; top: 0; z-index: 2; display: flex; gap: 6px;
  padding: 10px 12px; background: var(--panel); border-bottom: 1px solid var(--line);
}
.sheet-segmented button {
  flex: 1; min-height: 42px; border: 1px solid var(--line-strong); background: #fff; color: var(--ink-soft);
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; border-radius: 4px;
}
.sheet-segmented button.active { background: var(--ink); color: var(--paper); border-color: var(--ink); }

/* peek content */
.peek, .peek-empty { display: flex; flex-direction: column; gap: 6px; }
.peek-trip { font-family: var(--display); font-weight: 700; font-size: 20px; text-transform: uppercase; letter-spacing: 0.02em; line-height: 1.05; }
.peek-risk { display: flex; align-items: center; gap: 8px; }
.peek-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.peek-status { font-family: var(--mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.peek-progress { font-family: var(--mono); font-size: 12px; color: var(--ink-soft); }
.peek-run { align-self: flex-start; margin-top: 2px; }
.peek-empty .peek-title { font-family: var(--display); font-weight: 700; font-size: 18px; text-transform: uppercase; letter-spacing: 0.02em; }
.peek-empty .peek-sub { font-size: 12.5px; color: var(--ink-soft); }

/* ---------- Touch sizing + readability (phone base) ---------- */
input, select, textarea { font-size: 16px; }   /* 16px stops iOS Safari focus-zoom */
.btn { min-height: 44px; }
.btn.small { min-height: 38px; }
.layer-toggles { font-size: 14px; }
.layer-toggles label { padding: 8px 0; }
.layer-toggles input { width: 18px; height: 18px; }
.layer-note { font-size: 12px; color: var(--ink-soft); margin-top: 8px; }
.field input, .field select, .field textarea { padding: 9px 10px; }
.trip-item { padding: 11px 13px; }
.section { padding: 12px 14px; }
.status-banner .value { font-size: 22px; }

/* full-page views stack to one column on phone */
.detail-page { display: block; height: 100%; overflow-y: auto; }
.detail-main, .detail-side { overflow: visible; height: auto; }
.detail-main { padding: 16px 14px; }
.detail-side { padding: 12px 14px; border-top: 1px solid var(--line-strong); }
.detail-h1 { font-size: 24px; }
.settings-page { padding: 16px 14px; }
.settings-grid { grid-template-columns: 1fr; }
.auth-screen { width: 100%; max-width: 420px; margin: 6vh auto; padding: 24px 18px; }

/* ===== TABLET (>=700px): plan rail + map/conditions stacked ===== */
@media (min-width: 700px) {
  .brand-name { font-size: 22px; }
  .brand-sub { display: block; font-family: var(--mono); font-size: 10px; color: #b9c0b4; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 1px; }
  .backend-host { display: inline; }
  .hide-on-mobile { display: inline-flex; }

  .dashboard { display: grid; grid-template-columns: 300px 1fr; grid-template-rows: 58% 42%; }
  .dashboard .panel-left {
    display: block; grid-column: 1; grid-row: 1 / span 2;
    overflow-y: auto; background: var(--panel); border-right: 1px solid var(--line-strong);
  }
  .panel-center { position: relative; inset: auto; grid-column: 2; grid-row: 1; }
  .dashboard .panel-right {
    display: block; grid-column: 2; grid-row: 2;
    overflow-y: auto; background: var(--panel); border-top: 1px solid var(--line-strong);
  }
  .map-overlay-tl { max-width: 420px; width: calc(100% - 20px); }
  .map-overlay-br { display: block; }
  .bottom-sheet { display: none; }

  .settings-grid { grid-template-columns: 1fr 1fr; }
  .detail-page { display: grid; grid-template-columns: 1fr 1fr; height: 100%; overflow: hidden; }
  .detail-main, .detail-side { overflow-y: auto; height: auto; }
  .detail-side { border-top: none; border-left: 1px solid var(--line-strong); }
}

/* ===== DESKTOP (>=1100px): original 3-column grid ===== */
@media (min-width: 1100px) {
  .dashboard { grid-template-columns: 330px 1fr 430px; grid-template-rows: none; }
  .dashboard .panel-left { grid-column: 1; grid-row: auto; }
  .panel-center { grid-column: 2; grid-row: auto; }
  .dashboard .panel-right { grid-column: 3; grid-row: auto; border-top: none; border-left: 1px solid var(--line-strong); }
  .btn { min-height: 40px; }
  .detail-page { grid-template-columns: 1fr 460px; }
  input, select, textarea { font-size: 13px; }
  .field input, .field select, .field textarea, .search-box input { font-size: 14px; }
}
```

- [ ] **Step 3: Build + visual check**

Run: `cd frontend && npm run build`
Then `cd frontend && npm run dev` and open the app. At a narrow window (~375px): full-screen map, sheet peeking from the bottom with the grip; drag/tap the grip to expand to half/full; segmented Conditions/Plan switches content. At ~768px: plan rail + map(top)/conditions(bottom). At ≥1100px: original 3-column.
Expected: all three layouts render; no horizontal scrollbar at 375px.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(frontend): mobile-first layout + bottom-sheet styles"
```

---

## Task 6: Dashboard readability on phone

Stack `.kv` data grids to one column on phone (restore two-column at ≥700px) and make the dashboard action row stack full-width.

**Files:**
- Modify: `frontend/src/index.css` (the existing `.kv` block, ~line 367)
- Modify: `frontend/src/components/ConditionDashboard.tsx` (action row)

- [ ] **Step 1: Replace the existing `.kv` block** in `index.css` with the mobile-first version:

```css
.kv { display: grid; grid-template-columns: 1fr; gap: 1px 12px; font-size: 12.5px; }
.kv .k { font-family: var(--mono); font-size: 10.5px; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 7px; }
.kv .k:first-child { margin-top: 0; }
.kv .v { font-family: var(--mono); font-size: 12px; }
@media (min-width: 700px) {
  .kv { grid-template-columns: auto 1fr; gap: 2px 12px; }
  .kv .k { margin-top: 0; align-self: baseline; }
}
```

- [ ] **Step 2: Add the `.dash-actions` rule** to `index.css` (place near the `.btn` rules):

```css
.dash-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.dash-actions .btn { flex: 1 1 auto; }
@media (min-width: 700px) { .dash-actions .btn { flex: 0 0 auto; } }

/* comfortable tap area for secondary source links inside dense meta rows */
.conn-row .meta a, .f-src a { display: inline-flex; align-items: center; min-height: 34px; }
```

- [ ] **Step 3: Use `.dash-actions` in `ConditionDashboard.tsx`.** Replace:

```tsx
        <div style={{ display: "flex", gap: 8 }}>
```

with:

```tsx
        <div className="dash-actions">
```

(The matching `</div>` stays.)

- [ ] **Step 4: Build + visual check**

Run: `cd frontend && npm run build`
At 375px: open Conditions, run/inspect a check — key/value rows stack (label above value), no horizontal scroll; Run/Print buttons fill the width. At ≥700px the kv rows are two-column again.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/components/ConditionDashboard.tsx
git commit -m "feat(frontend): phone-readable kv stacking and full-width dashboard actions"
```

---

## Task 7: Touch + breakpoint alignment for remaining components

**Files:**
- Modify: `frontend/src/components/TripForm.tsx`
- Modify: `frontend/src/components/AuthScreen.tsx`
- Modify: `frontend/src/index.css` (elevation row + search results)

- [ ] **Step 1: TripForm — make the elevation inputs wrap-safe.** Change the elevation `field-row`:

```tsx
        <div className="field-row">
          <input placeholder="Trailhead" inputMode="numeric" value={trailheadFt} onChange={(e) => setTrailheadFt(e.target.value.replace(/[^\d]/g, ""))} />
```

to add the `elevation` class:

```tsx
        <div className="field-row elevation">
          <input placeholder="Trailhead" inputMode="numeric" value={trailheadFt} onChange={(e) => setTrailheadFt(e.target.value.replace(/[^\d]/g, ""))} />
```

- [ ] **Step 2: AuthScreen — replace the fixed inline margin with a class.** Change:

```tsx
    <div className="auth-screen" style={{ maxWidth: 360, margin: "8vh auto", padding: 24 }}>
```

to:

```tsx
    <div className="auth-screen">
```

(`.auth-screen` is already defined in Task 5.)

- [ ] **Step 3: Add the elevation + search-results rules** to `index.css`:

```css
.field-row.elevation { flex-wrap: wrap; }
.field-row.elevation input { flex: 1 1 84px; min-width: 84px; width: auto; }

.search-results { max-height: 50vh; overflow-y: auto; }
.search-results .res { padding: 11px 12px; }   /* larger tap target */
```

- [ ] **Step 4: Build + visual check**

Run: `cd frontend && npm run build`
At 375px: open the auth screen (Log in) — centered card, full-width inputs, no clipping. In the Plan tab, the New-trip elevation inputs fit/wrap without overflow. Settings (gear) shows a single column; Trip detail (Detail/history on a saved trip) stacks main over side. Search results scroll within 50vh.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TripForm.tsx frontend/src/components/AuthScreen.tsx frontend/src/index.css
git commit -m "feat(frontend): touch-friendly auth, elevation inputs, and search results"
```

---

## Task 8: Visual elevation polish

Unify focus/active feedback, add a subtle topo motif to the sheet header, and honor reduced motion — all within the existing identity.

**Files:**
- Modify: `frontend/src/index.css` (append a polish block near the end, before the scrollbars section)

- [ ] **Step 1: Append the polish block** to `index.css`:

```css
/* ---------- Interaction polish ---------- */
:where(button, a, input, select, textarea):focus-visible {
  outline: 2px solid var(--teal); outline-offset: 1px; border-radius: 3px;
}
.btn:active { transform: translateY(1px); }
.trip-item:active { border-color: var(--ink-soft); }
.sheet-segmented button:active { transform: translateY(1px); }

/* subtle contour motif on the sheet header, echoing the desktop .contour-bg */
.sheet-grip, .sheet-peek {
  background-image: repeating-radial-gradient(
    ellipse 360px 180px at 80% -40%,
    transparent 0px, transparent 26px,
    rgba(31, 36, 31, 0.04) 26px, rgba(31, 36, 31, 0.04) 27px
  );
}

@media (prefers-reduced-motion: reduce) {
  .bottom-sheet { transition: none; }
  .btn:active, .sheet-segmented button:active { transform: none; }
}
```

- [ ] **Step 2: Build + visual check**

Run: `cd frontend && npm run build`
Keyboard-tab through controls — visible teal focus ring. Buttons depress slightly on press. Sheet header shows a faint contour texture. With OS "reduce motion" on, the sheet snaps without sliding.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(frontend): focus-visible, press states, sheet contour motif, reduced-motion"
```

---

## Task 9: Verification — build + responsive screenshots

**Files:**
- Create (temporary): `frontend/scripts/shots.mjs`

- [ ] **Step 1: Full build/typecheck**

Run: `cd frontend && npm run build`
Expected: `tsc -b` clean and `vite build` reports `✓ built` with a `dist/` output.

- [ ] **Step 2: Create the screenshot script** `frontend/scripts/shots.mjs`:

```js
import { chromium } from "playwright";

const BASE = process.env.SHOT_URL || "http://localhost:4173";
const SIZES = [
  { name: "phone-375", width: 375, height: 812 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1280", width: 1280, height: 900 },
];

const browser = await chromium.launch();
for (const s of SIZES) {
  const page = await browser.newPage({ viewport: { width: s.width, height: s.height } });
  await page.goto(BASE, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(1500); // let the map settle
  await page.screenshot({ path: `shots/${s.name}.png`, fullPage: false });
  await page.close();
  console.log("captured", s.name);
}
await browser.close();
```

- [ ] **Step 3: Serve the build and capture (best-effort).**

```bash
cd frontend
npm run preview &          # serves dist/ on http://localhost:4173
npx -y playwright@latest install chromium
mkdir -p shots
node scripts/shots.mjs
```

Expected: `frontend/shots/phone-375.png`, `tablet-768.png`, `desktop-1280.png`.
The app renders without a backend (it shows a "backend offline" banner; the shell, map, and bottom sheet still render). Stop the preview server when done (`kill %1`).

If Playwright cannot be installed in this environment, record that fact and instead walk the **manual checklist** below in a browser at the three widths.

- [ ] **Step 4: Review screenshots and fix obvious issues.** Open each PNG. Manual checklist:
  - **375px:** no horizontal scrollbar anywhere; sheet peek shows trip name + risk dot + Run button; grip drags to half/full; segmented Conditions/Plan toggles; kv rows stacked; buttons ≥44px; topbar not overflowing.
  - **768px:** plan rail + map(top)/conditions(bottom); no sheet; search box visible.
  - **1280px:** original 3-column grid intact; conditions panel on the right.

  For any visual defect found, fix it in `index.css` (or the relevant component) and re-run Steps 1 + 3.

- [ ] **Step 5: Remove the temporary script + artifacts and commit.**

```bash
cd frontend && rm -rf scripts/shots.mjs shots
git add -A
git commit -m "chore(frontend): verify responsive layout at 375/768/1280"
```

(If `frontend/shots/` was added to `.gitignore` instead of deleted, note it. Do not commit PNG artifacts.)

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task(s) |
|---|---|
| Mobile-first breakpoints (phone / tablet / desktop) | 5 |
| Map primary on phone; full-bleed | 4, 5 |
| Draggable bottom sheet (peek/half/full) | 3, 4, 5 |
| Safety/risk always visible (peek banner) | 4 (`SheetPeek`), 5 |
| Segmented Conditions/Plan; default Plan→Conditions on select | 4 |
| Reusable Plan content (no duplication) | 2 (`PlanPanel`) |
| Map not remounted across breakpoints | 1 (`useIsPhone`), 4 |
| Dashboard readable, no horizontal scroll | 6 |
| Touch targets ≥44px; 16px inputs | 5, 6, 7 |
| TripForm / SavedTrips / Settings / TripDetail / Auth / Search responsive | 5, 6, 7 |
| Topbar compact on phone | 5 |
| Preserve desktop 3-column | 5 (≥1100 query) |
| Visual elevation within identity (focus, press, contour, risk colors) | 8 |
| Remove old tabbar/compactPanel | 4 |
| Build/typecheck passes | every task |
| Screenshots at 375/768/1280 + fixes | 9 |

No uncovered requirements.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step contains complete code.

**3. Type consistency:** `SheetSnap` defined in Task 3, imported in Task 4. `LayerState` imported from `MapView` in Task 2 (matches existing export). `PlanPanel` prop names (`onSelectTrip`, `onLayersChange`, `selectedTripId`, `loggedIn`) are identical in its definition (Task 2) and both call sites (Tasks 2 and 4). `SheetPeek`/`LoggedOutConditions` props match their call sites. `concernColor` retained in App and reused by `SheetPeek`. `ConditionDashboard` prop list unchanged from the existing component.
