# SummitSignal — Mobile-First Responsive Redesign

**Date:** 2026-06-13
**Scope:** Frontend only (`frontend/`). No backend or API-contract changes.
**Decision basis:** Fresh redesign (clean slate) · draggable bottom sheet on phone · elevate visuals within the existing topo/paper identity.

## Goal

Make SummitSignal feel good on phone (360–430px), tablet, and desktop. Treat the
map as the primary mobile surface. Keep safety/risk information visible without
extra taps. Preserve (and lightly refine) the desktop layout. Keep the outdoors /
navigation / weather visual identity: practical, trustworthy, polished — not
flashy SaaS-generic.

## Current state (audit)

The working tree already contains an uncommitted mobile pass (`index.html`,
`App.tsx`, `index.css`) that added a bottom tab bar + tab-toggled bottom sheets,
a tablet 2-column grid, and touch tuning. This redesign **replaces the tab model
with a draggable sheet**, but keeps the good infrastructure already there:
`viewport-fit=cover`, `theme-color`, safe-area insets, 16px inputs (no iOS zoom),
44px tap targets. The CSS is currently desktop-first (`max-width` queries) and
will be inverted to mobile-first.

Weak spots this redesign fixes:
- `.kv` data grids (`auto 1fr`) cramp at 360px; long source URLs/values.
- Risk info requires a tab tap (violates "don't hide safety behind clicks").
- `TripDetail` / `SettingsView` use stray one-off breakpoints (1000 / 900px) not
  aligned to the system.
- "click map to set trip point" hint hidden on mobile with no touch equivalent.
- `AuthScreen` uses a fixed `8vh` inline margin.

## Breakpoint system (mobile-first)

Base styles target the phone; `min-width` queries scale up.

| Tier | Range | Layout |
|------|-------|--------|
| Phone | base → 699px | Full-bleed map + one draggable bottom sheet |
| Tablet | ≥ 700px | 2-column: Plan rail (left, full height) · map (top) + conditions (bottom) on the right |
| Desktop | ≥ 1100px | Original 3-column grid (330 / 1fr / 430), preserved |

The bottom sheet is **phone-only**. Tablet and desktop use grid panels.

## Phone interaction model — the draggable bottom sheet

A reusable `BottomSheet` component renders over a permanently-mounted, full-screen
`MapView`. Driven by Pointer Events (touch + mouse), animated via CSS transform,
`prefers-reduced-motion` aware. Three snap points:

- **Peek (~156px, always visible).** Grip handle · selected trip name (or "Search
  or tap the map to start") · compact **color-coded overall risk banner** ·
  primary action (`Run check`, or live `Running… N/M` progress) · freshness
  ("checked 2h ago" / "stale"). This is how safety stays visible with zero taps.
- **Half (~55% height).** Peek header + segmented control **[ Conditions | Plan ]**
  + the active region's content, scrollable inside the sheet.
- **Full (top edge at the topbar).** Same content, maximized for reading flags,
  AI summary, and source results.

Default segmented tab: **Plan** when no trip is selected; switches to
**Conditions** when a trip is selected (selecting a trip also expands the sheet
from peek to half). The user can switch tabs freely thereafter.

Interaction: drag the grip to move freely; release snaps to the nearest point;
tapping the grip cycles upward (peek → half → full). No heavy scrim — the map
stays glanceable so it remains the primary surface. The search bar floats on the
map (z-index below the sheet); when the sheet is full it is covered, which is
acceptable (drag down to search).

Accessibility: sheet has `role="dialog"`; the grip is a `<button>` with an
`aria-label` and `aria-expanded`; the segmented control is a `tablist` with
`tab`/`tabpanel` semantics.

## Component architecture changes

- **New `useIsPhone()` hook** — `matchMedia('(max-width: 699px)')` with a change
  listener. Chooses the render tree without remounting `MapView` (remounting
  MapLibre is expensive and must be avoided).
- **New `BottomSheet.tsx`** — generic snap/drag shell. Props: snap state +
  setter, a `peek` slot (always-visible header), and children (expanded content).
  Owns the drag math and snap-on-release.
- **New `PlanPanel.tsx`** — extract *New trip + Saved trips + Map layers* out of
  `App.tsx` so the identical content renders in both the desktop left panel and
  the phone sheet, with no JSX duplication.
- **Refactor `App.tsx`** — dashboard view renders:
  - `MapView` (always mounted) + floating `SearchBar`.
  - If phone: `BottomSheet` with peek header + segmented `[Conditions | Plan]`
    toggling `ConditionDashboard` / `PlanPanel`.
  - Else: `.panel-left` (`PlanPanel`) + `.panel-right` (`ConditionDashboard`) in
    the grid.
  - **Remove** the bottom-tabbar / `compactPanel` mechanism added in the current
    uncommitted pass.
- Settings / Auth / TripDetail remain full-screen views that replace the
  dashboard (reached via topbar nav / saved-trip detail button), each with a back
  affordance and single-column scroll on phone.

## Dashboard readability on phone (no horizontal scroll)

- `.kv` grids stack to a single column on phone (mono label caption above value),
  so long values never force horizontal scroll.
- Connector rows, flags, and source links get ≥44px tap targets; long URLs/values
  wrap (`overflow-wrap: anywhere`, reinforced).
- Action buttons (`Run check` / `Print report`) stack full-width on phone.

## Other components (touch + breakpoint alignment)

- **TripForm** — elevation 3-input row wraps gracefully at 360px; file input and
  Save button touch-sized.
- **SavedTrips** — card items, clear selected state, ≥44px "Detail / history" and
  "Re-check all" buttons.
- **SettingsView / TripDetail** — re-aligned to the 700 / 1100 breakpoints (drop
  the stray 900 / 1000px ones); single-column stack on phone; full-width actions;
  tappable history rows.
- **AuthScreen** — replace fixed `8vh` inline margin with a responsive centered
  card.
- **SearchBar** — capped results height + scroll so the list never exceeds the
  viewport on phone.
- **Topbar** — compact on phone: brand + backend status dot + Settings + auth
  button.

## Visual elevation (within the existing identity)

No new palette or fonts. Keep paper-chart background, blaze-orange accent, IBM
Plex Mono data readouts, Barlow Condensed display, Inter body. Refinements:

- Tighten the type and spacing scale for rhythm.
- Unify the **risk color system** across banner, badges, dots, and the sheet peek
  chip: major = blaze orange (`--accent`), moderate = amber, ok = teal, unknown =
  gray, failed = red.
- Refine card and sheet chrome: rounded sheet top, styled grip, subtle contour
  motif on the sheet header.
- Add `:active` press states and `focus-visible` outlines (teal).

## Out of scope (unchanged)

Backend, API contracts, data flow, and `MapView`'s map logic (only its overlay /
CSS may change). Edits are made in place over the already-uncommitted files.

## Verification

1. `npm run build` (`tsc -b && vite build`) must pass with no type errors.
2. Best-effort screenshots at **375 / 768 / 1280px** via Playwright against the
   Vite dev server. The UI renders without a backend (it shows an "offline" banner
   but the shell, map, auth, and layout still render). If Playwright is
   unavailable, state that and fall back to a documented manual checklist.
3. Fix obvious visual issues found during testing.

## Risks / notes

- Drag-sheet gesture handling is the most involved new code. Mitigation: keep snap
  logic simple (three fixed targets, nearest-on-release), gate transitions on
  `prefers-reduced-motion`, and make the grip tappable as a non-gesture fallback.
- `MapView` must not remount across breakpoint changes — `useIsPhone` only swaps
  the surrounding panels/sheet, never the map element.
