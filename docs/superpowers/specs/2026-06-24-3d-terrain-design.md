# 3D Terrain View — Design

Date: 2026-06-24
Status: Approved (design)

## Goal

Let the user tilt the map into a true 3D terrain view: the basemap drapes over
real elevation from the existing DEM, so ridges, valleys, and peaks rise in
relief and routes drape along the ground. A single toggle in the Layers panel's
Terrain group turns it on/off.

## Decisions

- Control: a **"3D terrain" checkbox in the Layers panel → Terrain group**
  (reuses the existing layer toggle + ⓘ-tooltip plumbing). No new control UI.
- Vertical exaggeration: **fixed ~1.4×** (no slider).
- Off by default each session; **not persisted** across reloads.
- All screen sizes; opt-in. No backend changes.

## Existing code (relevant)

- `frontend/src/components/MapView.tsx`:
  - Adds a `raster-dem` source `dem` (`getDemSource()`) on map load, currently
    feeding only hillshade + the slope/aspect/contour protocols.
  - `OVERLAY_RENDER` maps registry overlay ids → MapLibre layer ids; `syncVisibility`
    iterates `OVERLAY_RENDER` and toggles visibility/opacity from `layerState`.
  - `syncAll()` runs on `load` and is re-run from the `styledata` handler after a
    basemap `setStyle` (which re-adds overlay sources). Basemap swaps go through a
    `layerState` effect that calls `map.setStyle(...)`.
  - NavigationControl has `showCompass: true` (manual rotate/pitch already works).
- `frontend/src/layers/registry.ts` — `LAYERS` array; `OVERLAY_LAYERS = LAYERS
  .filter(l => l.group !== "basemap" && !l.comingSoonPhase)`; terrain group holds
  `overlay.hillshade/slope/aspect/contours`.
- `frontend/src/layers/types.ts` — `LayerKind` union; `LayerDescriptor` has
  `description?`.
- `frontend/src/components/LayersControl.tsx` — renders each `OVERLAY_LAYERS`
  entry as a checkbox (+ optional legend/opacity/ⓘ tooltip). It does not switch
  on `kind`, so a new kind needs no LayersControl change.
- `frontend/src/layers/registry.test.ts` — asserts every overlay has a non-empty
  description.

## Components / changes

### 1. Registry entry (`registry.ts`) + new kind (`types.ts`)
- Add `"terrain-3d"` to the `LayerKind` union in `types.ts`.
- Add, at the TOP of the terrain group in `LAYERS`:
  ```ts
  { id: "overlay.terrain3d", group: "terrain", kind: "terrain-3d", label: "3D terrain",
    description: "Tilts the camera and drapes the map over real elevation (DEM) so terrain rises in relief. Heavier on the GPU.",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false, legend: { kind: "none" } },
  ```
  It flows into `OVERLAY_LAYERS` automatically and renders as a Terrain-group
  checkbox with the ⓘ tooltip. It is intentionally NOT added to
  `OVERLAY_RENDER`, so `syncVisibility` ignores it.

### 2. MapView 3D handling
- Add `sync3DTerrain()`:
  - Reads `on = !!layerState["overlay.terrain3d"]?.visible`.
  - On: if `map.getSource("dem")`, `map.setTerrain({ source: "dem", exaggeration: 1.4 })`;
    apply sky; if `map.getPitch() < 1`, `map.easeTo({ pitch: 60, duration: 600 })`.
  - Off: `map.setTerrain(null)`; remove sky; if `map.getPitch() > 1`,
    `map.easeTo({ pitch: 0, duration: 600 })`.
- Sky helper (best-effort, guarded):
  - On: `if (typeof map.setSky === "function") map.setSky({ ...atmosphere })`.
  - Off: `if (typeof map.setSky === "function") map.setSky({})` (or clear).
  - If `setSky` is unavailable, skip silently — terrain still works.
- Call `sync3DTerrain()` from `syncAll()` (so it re-applies after `load` and after
  basemap `setStyle`/`styledata`), and add it to the prop-driven `layerState`
  effect so toggling takes effect live. `setTerrain`/`easeTo` are guarded by the
  `dem` source / map existence; never throws.

Constants: `EXAGGERATION = 1.4`, `DEFAULT_PITCH = 60`.

### 3. No other UI changes
LayersControl, App, and panel layout are untouched (the toggle is data-driven).

## Behavior notes / edge cases

- Manual tilt/rotate via the compass still works in both modes; toggling 3D off
  forces pitch back to 0 (true top-down).
- Hillshade + 3D together = real relief plus shading (looks good; allowed).
- Slope/aspect/contour overlays drape onto the 3D surface automatically.
- Basemap swap while 3D is on: `setStyle` clears terrain; `styledata` → `syncAll`
  → `sync3DTerrain` re-applies it; camera pitch is preserved by `setStyle`.
- Point-click elevation sampling (`pointSample`) uses the same DEM — unaffected.

## Testing

- `registry.test.ts`: keep the description assertion (now also guards the new
  entry); add an assertion that `overlay.terrain3d` exists with `group: "terrain"`
  and `kind: "terrain-3d"`.
- `tsc --noEmit`, `npm run build`, existing `vitest` pass.
- WebGL/camera behavior (terrain mesh, sky, pitch) is verified **visually** —
  jsdom has no WebGL/layout engine, so it can't be unit-tested. Manual check:
  toggle on → map tilts and terrain rises; toggle off → returns to flat top-down;
  swap basemap while on → terrain persists; works without a MapTiler key (AWS
  Terrarium DEM) and better with one.

## Out of scope

Exaggeration slider; persistence across reloads; custom max-pitch; terrain from a
non-DEM source; a separate on-map 2D/3D button.
