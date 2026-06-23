# Layer Description Tooltips — Design

Date: 2026-06-23
Status: Approved (design)

## Goal

Help users understand what each map overlay does. Add a small ⓘ info icon next
to each overlay in the Layers panel that reveals a short, concise description on
hover or keyboard focus — enough to convey what the layer shows and how to use
it, without leaving the panel.

## Decisions

- Trigger/style: a focusable ⓘ icon per overlay row that shows a **themed**
  tooltip box on hover AND keyboard focus (pure CSS; no JS state, no positioning
  library, no native `title`).
- Coverage: **overlays only** (the 12 `OVERLAY_LAYERS`). Basemaps and "coming
  soon" layers are left as-is.
- Planning-aid tone preserved where relevant (e.g. fire/avalanche layers are
  described as indicative, not authoritative).

## Existing code (relevant)

- `frontend/src/layers/types.ts` — `LayerDescriptor` already declares an optional
  `description?: string` field (currently unused). No type change needed.
- `frontend/src/layers/registry.ts` — `LAYERS` array; `OVERLAY_LAYERS =
  LAYERS.filter(l => l.group !== "basemap" && !l.comingSoonPhase)`.
- `frontend/src/components/LayersControl.tsx` — renders each overlay row
  (`layers-row-block` → `layers-row` with the checkbox + `{l.label}`, then
  optional `<Legend>` and opacity slider). The ⓘ goes right after `{l.label}`.
- App stylesheet: `frontend/src/index.css` (imported by `main.tsx`).

## Components / changes

### 1. Registry copy (`registry.ts`)
Add a one-sentence `description` to each of the 12 overlays:
- `overlay.perimeters` (Fire perimeters) — official/active large-fire boundary
  polygons; indicative, verify with authorities.
- `overlay.fires` (Active fires) — recent VIIRS satellite heat detections;
  indicative points, not official fire boundaries.
- `overlay.gpx` (GPX route) — the route attached to the selected trip
  (uploaded or built).
- `overlay.savedTrips` (Saved trips) — markers for your saved trip points.
- `overlay.point` (Selected point) — the point you last clicked/searched, used
  for the point panel and new trips.
- `overlay.hillshade` (Hillshade) — shaded relief that makes terrain shape
  readable.
- `overlay.slope` (Slope angle) — shades steepness; reds (≈35°+) flag avalanche-
  and fall-prone slopes.
- `overlay.aspect` (Aspect) — colors the compass direction a slope faces (sun/
  snow/wind exposure).
- `overlay.contours` (Contours) — elevation contour lines (40 ft / 200 ft index).
- `overlay.aqi` (Air quality) — nearby ground-station air-quality index readings.
- `overlay.avalanche` (Avalanche danger) — forecast regional danger rating where
  a center publishes it; check the official forecast.
- `overlay.snow` (Snow depth) — feeds the point panel with modeled snow depth (no
  map drawing).

(Exact wording finalized during implementation; each must be short and concise.)

### 2. `InfoTip` component (`frontend/src/components/InfoTip.tsx`)
Small, reusable, presentational:
- Renders a focusable ⓘ trigger (`tabIndex={0}`, `role="img"`,
  `aria-label={text}`) wrapping a tooltip bubble element.
- Bubble shows via CSS on `:hover` and `:focus-within` — no React state.
- Props: `{ text: string }`.

### 3. `LayersControl.tsx`
After `{l.label}` in the overlay row, render `{l.description ? <InfoTip
text={l.description} /> : null}`. No other changes.

### 4. Styles (`index.css`)
- `.info-tip` — inline, small, muted ⓘ; cursor help; focus ring.
- `.info-tip-bubble` — absolutely-positioned themed box (panel bg, border,
  small text, ~200 px wide, subtle shadow); hidden by default, shown on
  hover/focus. Opens **leftward/below** the icon because the Layers panel sits at
  the top-right of the viewport (prevents off-screen clipping).

## Testing

- `frontend/src/layers/registry.test.ts` (new): assert every `OVERLAY_LAYERS`
  entry has a non-empty, trimmed `description` (guards against future overlays
  shipping without help text).
- `npx tsc --noEmit` and `npm run build` clean; existing `vitest` suite still
  passes.

## Out of scope

Basemap and coming-soon descriptions; per-layer links/help pages; i18n; any
change to layer behavior, ordering, legends, or the map render.
