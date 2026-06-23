# Collapsible Side Panels — Design

Date: 2026-06-23
Status: Approved (design)

## Goal

Let the user collapse/expand the left (Plan) and right (This-point + Conditions)
side panels independently so the map gets more room. State persists across
reloads. Phone (bottom sheet) is unchanged.

## Decisions

- **Independent** per-panel collapse (left and right separately), persisted to
  `localStorage`.
- **Reopen affordance:** a slim labeled chevron tab on the collapsed edge of the
  map; **collapse affordance:** a chevron button at each panel's inner edge.
- **Scope:** desktop (≥1100px, 3-column) and tablet (≥700px). Phone untouched.
- Animated slide via CSS grid track transitions; the map resizes to fill.

## Existing layout (relevant)

- `frontend/src/App.tsx` renders, inside `{view === "dashboard"}` →
  `<div className="dashboard">`: `<aside className="panel-left">` (PlanPanel),
  `<main className="panel-center">` (MapView + map overlays), and
  `<aside className="panel-right">` (This-point + Conditions). Both asides are
  gated on `!isPhone`.
- `frontend/src/index.css`:
  - Phone base: panels `display:none`, `.panel-center` absolute full-bleed,
    `.bottom-sheet` used instead.
  - Tablet `@media (min-width:700px)`: `.dashboard` grid
    `grid-template-columns: 300px 1fr; grid-template-rows: 58% 42%`. `panel-left`
    spans both rows (left rail); `panel-center` is row 1 col 2; `panel-right` is
    row 2 col 2 (a **bottom** strip).
  - Desktop `@media (min-width:1100px)`: `grid-template-columns: 330px 1fr 430px;
    grid-template-rows: none` (true 3 columns).
- `MapView` keeps its map in a container ref; MapLibre's `trackResize` watches
  the **window**, not the container, so a grid collapse won't auto-resize it.

## Components / changes

### 1. Pure layout helpers (`frontend/src/lib/panelLayout.ts`)
- `dashboardClasses(leftCollapsed: boolean, rightCollapsed: boolean): string` —
  returns `"dashboard"` plus `" is-left-collapsed"` / `" is-right-collapsed"` as
  applicable.
- `readPanelCollapsed(side: "left" | "right"): boolean` and
  `writePanelCollapsed(side, value)` — localStorage keys
  `summitsignal_panel_left` / `summitsignal_panel_right` ("1"/"0"), guarded so a
  missing/throwing localStorage returns `false`.

### 2. `usePanelCollapse` hook (`frontend/src/hooks/usePanelCollapse.ts`)
Wraps two booleans initialized from `readPanelCollapsed`, persists each via
`writePanelCollapsed` in an effect, and exposes
`{ leftCollapsed, rightCollapsed, toggleLeft, toggleRight }`.

### 3. App wiring (`App.tsx`)
- Call `usePanelCollapse()`.
- Set the dashboard wrapper className via `dashboardClasses(...)`.
- Render a collapse chevron button at each panel's inner edge (inside each
  `<aside>`): left button `‹`, right button `›` (the CSS rotates/relabels the
  right one to `⌄` on tablet where it collapses downward).
- Render two reopen tabs inside `.panel-center` (alongside the existing
  SearchBar / Layers / RouteBuilder overlays), each shown only when its panel is
  collapsed and `!isPhone`: a left tab ("Plan ›") and a right tab ("‹ Info").
  Clicking a tab calls the matching toggle.

### 4. CSS (`index.css`)
- `.dashboard { transition: grid-template-columns .28s ease, grid-template-rows .28s ease; }`
- Tablet block:
  - `.dashboard.is-left-collapsed { grid-template-columns: 0 1fr; }`
  - `.dashboard.is-right-collapsed { grid-template-rows: 1fr 0; }` (bottom strip
    collapses vertically)
- Desktop block:
  - `.dashboard.is-left-collapsed { grid-template-columns: 0 1fr 430px; }`
  - `.dashboard.is-right-collapsed { grid-template-columns: 330px 1fr 0; }`
  - both → `0 1fr 0`
- Panels need `overflow: hidden` while collapsing so content clips cleanly
  (the asides already scroll; ensure horizontal clip). Hide the panel's inner
  collapse button's hit area when width is 0 is automatic (clipped).
- `.panel-collapse-btn` — small, themed, positioned at the panel's inner edge.
- `.panel-reopen-tab` — slim themed tab; base `display: none`; shown in the
  ≥700 media query. Desktop: left tab pinned to map's left edge (vertically
  centered), right tab to map's right edge. Tablet: right tab pinned to the map's
  bottom edge with an up chevron. `z-index` above the map, below modals.

### 5. MapView resize (`MapView.tsx`)
Add a `ResizeObserver` on the container ref that calls `map.resize()` on size
changes (guarded for SSR/absent RO). Disconnect on unmount. Nothing else changes.

## Testing

- `frontend/src/lib/panelLayout.test.ts`: `dashboardClasses` for all four
  combinations; `read/writePanelCollapsed` round-trip and the
  localStorage-throws fallback (mock `localStorage`).
- `tsc --noEmit`, `npm run build`, existing `vitest` all pass.
- Layout/animation verified visually (jsdom has no layout engine); collapse,
  reopen, persistence-across-reload, and that the map fills the reclaimed space
  on both desktop and tablet, with the phone bottom sheet unaffected.

## Out of scope

Changes to panel contents; resizable/draggable panel widths; remembering scroll
position; collapsing on phone (keeps the bottom sheet); animating `display`.
