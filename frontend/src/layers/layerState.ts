import { LAYERS } from "./registry";
import type { LayerStateMap } from "./types";

/** Initial state from registry defaults — reproduces today's defaults
 *  (topo basemap, all overlays visible). */
export function seedLayerState(): LayerStateMap {
  const state: LayerStateMap = {};
  for (const l of LAYERS) {
    state[l.id] = { visible: l.defaultVisible, opacity: l.defaultOpacity };
  }
  return state;
}

export function setVisible(state: LayerStateMap, id: string, visible: boolean): LayerStateMap {
  return { ...state, [id]: { ...state[id], visible } };
}

export function setOpacity(state: LayerStateMap, id: string, opacity: number): LayerStateMap {
  return { ...state, [id]: { ...state[id], opacity } };
}

/** Basemaps are pick-one: selecting one makes the others invisible. */
export function selectBasemap(state: LayerStateMap, id: string): LayerStateMap {
  const next = { ...state };
  for (const l of LAYERS) {
    if (l.group === "basemap") next[l.id] = { ...next[l.id], visible: l.id === id };
  }
  return next;
}

export function activeBasemapId(state: LayerStateMap): string {
  const found = LAYERS.find((l) => l.group === "basemap" && state[l.id]?.visible);
  return found ? found.id : "basemap.topo";
}

/** Provider ids for currently-visible data-overlay layers (sent to point-context). */
export function enabledDataProviderIds(state: LayerStateMap): string[] {
  return LAYERS
    .filter((l) => l.kind === "data-overlay" && l.providerId && state[l.id]?.visible)
    .map((l) => l.providerId as string);
}
