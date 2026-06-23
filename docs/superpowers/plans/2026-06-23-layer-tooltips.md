# Layer Description Tooltips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small ⓘ info icon next to each map overlay in the Layers panel that reveals a short, themed description on hover or keyboard focus.

**Architecture:** Populate the already-existing `LayerDescriptor.description` field for the 12 overlay layers in the registry, then render a reusable pure-CSS `InfoTip` component beside each overlay label in `LayersControl`. No JS tooltip state, no positioning library, no native `title`.

**Tech Stack:** Vite + React + TypeScript, vitest. No new dependencies.

## Global Constraints

- No new dependencies (npm).
- Overlays only — do NOT add descriptions to basemaps or "coming soon" layers.
- Descriptions are short, single-sentence, and preserve the planning-aid tone for hazard layers (fire/avalanche described as indicative, not authoritative).
- Tooltip shows on BOTH hover and keyboard focus; carries the text via `aria-label` for screen readers.
- Do not change layer behavior, ordering, legends, opacity controls, or the map render.

---

## Task 1: Overlay descriptions in the registry + guard test

**Files:**
- Modify: `frontend/src/layers/registry.ts`
- Test: `frontend/src/layers/registry.test.ts` (create)

**Interfaces:**
- Consumes: `OVERLAY_LAYERS` exported from `registry.ts`; `LayerDescriptor.description?: string` (already in `layers/types.ts`).
- Produces: every entry in `OVERLAY_LAYERS` has a non-empty `description` string.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/layers/registry.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { OVERLAY_LAYERS } from "./registry";

describe("overlay layer descriptions", () => {
  it("every overlay has a non-empty description", () => {
    const missing = OVERLAY_LAYERS.filter((l) => !l.description || !l.description.trim());
    expect(missing.map((l) => l.id)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run src/layers/registry.test.ts 2>&1 | tail -12`
Expected: FAIL — the array of ids without descriptions is non-empty (no overlay has a description yet).

- [ ] **Step 3: Add a `description` to each overlay in `registry.ts`**

In `frontend/src/layers/registry.ts`, add a `description` field to each of the 12 overlay objects (the entries with `group` of `hazard`/`trip`/`terrain`/`weather`). Apply exactly these strings. For each object, insert `description: "..."` immediately after its `label: "...",`.

- `overlay.perimeters` (label "Fire perimeters"):
  `description: "Mapped boundaries of active large fires (WFIGS). Indicative — verify with official sources.",`
- `overlay.fires` (label "Active fires"):
  `description: "Recent satellite (VIIRS) heat detections — indicative points, not official fire boundaries.",`
- `overlay.gpx` (label "GPX route"):
  `description: "The route attached to the selected trip — an uploaded or in-app-built GPX line.",`
- `overlay.savedTrips` (label "Saved trips"):
  `description: "Markers for your saved trip points. Click one to select that trip.",`
- `overlay.point` (label "Selected point"):
  `description: "The point you last clicked or searched — used for the point panel and for new trips.",`
- `overlay.hillshade` (label "Hillshade"):
  `description: "Shaded relief that makes ridges, valleys, and terrain shape easy to read.",`
- `overlay.slope` (label "Slope angle"):
  `description: "Shades terrain steepness; reds (about 35°+) flag avalanche- and fall-prone slopes.",`
- `overlay.aspect` (label "Aspect"):
  `description: "Colors the compass direction each slope faces — useful for sun, snow, and wind exposure.",`
- `overlay.contours` (label "Contours"):
  `description: "Elevation contour lines (40 ft, with 200 ft index lines labeled).",`
- `overlay.aqi` (label "Air quality (AQI)"):
  `description: "Air-quality index from nearby ground stations — higher and redder means worse air.",`
- `overlay.avalanche` (label "Avalanche danger"):
  `description: "Regional avalanche danger rating where a forecast center publishes it. Always read the official forecast.",`
- `overlay.snow` (label "Snow depth (point panel)"):
  `description: "Adds modeled snow depth to the point panel; it does not draw on the map.",`

Example (the first overlay after editing):

```typescript
  { id: "overlay.perimeters", group: "hazard", kind: "data-overlay", label: "Fire perimeters",
    description: "Mapped boundaries of active large fires (WFIGS). Indicative — verify with official sources.",
    providerId: "wildfire", defaultVisible: false, defaultOpacity: 0.18, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#d84a1b", label: "Active perimeter" }] } },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run src/layers/registry.test.ts 2>&1 | tail -8`
Expected: 1 passed.

- [ ] **Step 5: Type-check**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layers/registry.ts frontend/src/layers/registry.test.ts
git commit -m "feat(layer-tooltips): overlay descriptions + guard test"
```

---

## Task 2: `InfoTip` component + LayersControl wiring + styles

**Files:**
- Create: `frontend/src/components/InfoTip.tsx`
- Modify: `frontend/src/components/LayersControl.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: `l.description` (set in Task 1) for each overlay in `LayersControl`.
- Produces: `InfoTip` default export — `InfoTip({ text }: { text: string })`.

- [ ] **Step 1: Create the `InfoTip` component**

Create `frontend/src/components/InfoTip.tsx`:

```typescript
interface Props {
  text: string;
}

// A small focusable ⓘ that reveals a themed tooltip on hover or keyboard focus.
// Pure CSS (see .info-tip / .info-tip-bubble in index.css) — no JS state.
export default function InfoTip({ text }: Props) {
  return (
    <span className="info-tip" tabIndex={0} role="img" aria-label={text}>
      <span aria-hidden="true">&#9432;</span>
      <span className="info-tip-bubble" role="tooltip">{text}</span>
    </span>
  );
}
```

- [ ] **Step 2: Wire it into `LayersControl`**

In `frontend/src/components/LayersControl.tsx`:

(a) Add the import after the existing `Legend` import (line 5):

```typescript
import InfoTip from "./InfoTip";
```

(b) The overlay row currently is:

```typescript
                <div key={l.id} className="layers-row-block">
                  <label className="layers-row">
                    <input
                      type="checkbox"
                      checked={!!st?.visible}
                      onChange={(e) => onToggle(l.id, e.target.checked)}
                    />
                    {l.label}
                  </label>
                  {l.legend ? <Legend legend={l.legend} /> : null}
```

Wrap the `<label>` and a new `InfoTip` in a flex head so the ⓘ sits next to the
name but OUTSIDE the `<label>` (clicking it must not toggle the checkbox). Replace
that opening portion with:

```typescript
                <div key={l.id} className="layers-row-block">
                  <div className="layers-row-head">
                    <label className="layers-row">
                      <input
                        type="checkbox"
                        checked={!!st?.visible}
                        onChange={(e) => onToggle(l.id, e.target.checked)}
                      />
                      {l.label}
                    </label>
                    {l.description ? <InfoTip text={l.description} /> : null}
                  </div>
                  {l.legend ? <Legend legend={l.legend} /> : null}
```

Leave the opacity-slider block and the closing `</div>` of `layers-row-block`
unchanged.

- [ ] **Step 3: Add styles**

Append to `frontend/src/index.css`:

```css
.layers-row-head { display: flex; align-items: center; gap: 4px; }

.info-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  color: var(--ink-soft, #6b6456);
  font-size: 12px;
  cursor: help;
  border-radius: 50%;
  outline: none;
}
.info-tip:focus-visible { box-shadow: 0 0 0 2px var(--accent, #d84a1b); }
.info-tip-bubble {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  width: 210px;
  padding: 7px 9px;
  background: var(--panel, #fbfaf6);
  color: var(--ink, #1f241f);
  border: 1px solid var(--line-strong, #d8d2c4);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.16);
  font-size: 11.5px;
  line-height: 1.35;
  z-index: 20;
  visibility: hidden;
  opacity: 0;
  transition: opacity 0.08s ease;
  pointer-events: none;
}
.info-tip:hover .info-tip-bubble,
.info-tip:focus .info-tip-bubble,
.info-tip:focus-within .info-tip-bubble {
  visibility: visible;
  opacity: 1;
}
```

(The bubble anchors to the icon's top-right and drops below, extending leftward,
so it never clips off the right edge of the top-right Layers panel.)

- [ ] **Step 4: Type-check and build**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3`
Expected: tsc clean; build succeeds.

- [ ] **Step 5: Run the existing test suite (no regression)**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx vitest run 2>&1 | tail -5`
Expected: all pass (existing tests + the registry test from Task 1).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InfoTip.tsx frontend/src/components/LayersControl.tsx frontend/src/index.css
git commit -m "feat(layer-tooltips): InfoTip component + layers panel wiring"
```

---

## Self-Review Notes (author)

- **Spec coverage:** registry copy → Task 1; `InfoTip` component → Task 2 step 1; LayersControl wiring → Task 2 step 2; styles (themed, opens leftward/below, hover+focus) → Task 2 step 3; guard test → Task 1; tsc/build/vitest → Task 2 steps 4-5. Basemaps and coming-soon untouched (no edits to those entries).
- **No placeholders:** all 12 description strings are spelled out; full code for the component, wiring, and CSS is included.
- **Type consistency:** `InfoTip({ text }: { text: string })` matches the `<InfoTip text={l.description} />` usage; `l.description` is `string | undefined` and guarded with `l.description ? ... : null`.
- **Accessibility:** ⓘ is focusable (`tabIndex={0}`), `aria-label={text}`, bubble shows on `:focus`/`:focus-within` as well as `:hover`; the ⓘ is outside the `<label>` so it doesn't toggle the checkbox.
