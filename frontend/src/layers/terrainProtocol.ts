import type maplibregl from "maplibre-gl";
import type { RequestParameters, GetResourceResponse } from "maplibre-gl";
import type { DemSourceConfig } from "./dem";

let worker: Worker | null = null;
let seq = 0;
const pending = new Map<number, (r: { ok: boolean; buf?: ArrayBuffer; error?: string }) => void>();

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL("./terrainWorker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (ev) => {
      const cb = pending.get(ev.data.id);
      if (cb) { pending.delete(ev.data.id); cb(ev.data); }
    };
  }
  return worker;
}

function parseTile(url: string): { z: number; x: number; y: number } {
  // e.g. "slope://10/163/395"
  const m = url.split("://")[1].split("/");
  return { z: Number(m[0]), x: Number(m[1]), y: Number(m[2]) };
}

/** Registers slope:// and aspect:// protocols that return colored raster tiles.
 *  Idempotent-ish: call once on map init with the active DEM config. */
export function registerTerrainProtocols(mlgl: typeof maplibregl, dem: DemSourceConfig) {
  const make = (kind: "slope" | "aspect") =>
    (params: RequestParameters, _abort: AbortController): Promise<GetResourceResponse<ArrayBuffer>> =>
      new Promise((resolve, reject) => {
        const { z, x, y } = parseTile(params.url);
        const id = ++seq;
        pending.set(id, (r) => {
          if (r.ok && r.buf) resolve({ data: r.buf });
          else reject(new Error(r.error || "terrain tile failed"));
        });
        getWorker().postMessage({ id, kind, z, x, y, demUrl: dem.tiles[0], encoding: dem.encoding });
      });
  mlgl.addProtocol("slope", make("slope"));
  mlgl.addProtocol("aspect", make("aspect"));
}
