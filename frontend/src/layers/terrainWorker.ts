/// <reference lib="webworker" />
import { decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel, tileCenterLat } from "./terrainMath";
import { slopeColor, aspectColor } from "./terrainColors";
import type { DemEncoding } from "./dem";

interface Req { id: number; kind: "slope" | "aspect"; z: number; x: number; y: number; demUrl: string; encoding: DemEncoding; }

const TILE = 256;

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

self.onmessage = async (ev: MessageEvent<Req>) => {
  const { id, kind, z, x, y, demUrl, encoding } = ev.data;
  try {
    const url = demUrl.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`dem ${resp.status}`);
    const bmp = await createImageBitmap(await resp.blob());
    const src = new OffscreenCanvas(TILE, TILE);
    const sctx = src.getContext("2d")!;
    sctx.drawImage(bmp, 0, 0, TILE, TILE);
    const px = sctx.getImageData(0, 0, TILE, TILE).data;

    const decode = encoding === "terrarium" ? decodeTerrarium : decodeMapbox;
    const elev = new Float32Array(TILE * TILE);
    for (let i = 0; i < TILE * TILE; i++) {
      elev[i] = decode(px[i * 4], px[i * 4 + 1], px[i * 4 + 2]);
    }
    const spacing = metersPerPixel(tileCenterLat(y, z), z);

    const out = new ImageData(TILE, TILE);
    const od = out.data;
    const at = (cx: number, cy: number) => elev[Math.min(TILE - 1, Math.max(0, cy)) * TILE + Math.min(TILE - 1, Math.max(0, cx))];
    for (let cy = 0; cy < TILE; cy++) {
      for (let cx = 0; cx < TILE; cx++) {
        const { slope, aspect } = pixelSlopeAspect(
          at(cx, cy), at(cx, cy - 1), at(cx + 1, cy), at(cx, cy + 1), at(cx - 1, cy), spacing,
        );
        const [r, g, b] = hexToRgb(kind === "slope" ? slopeColor(slope) : aspectColor(aspect));
        const o = (cy * TILE + cx) * 4;
        od[o] = r; od[o + 1] = g; od[o + 2] = b; od[o + 3] = 255;
      }
    }
    const dst = new OffscreenCanvas(TILE, TILE);
    dst.getContext("2d")!.putImageData(out, 0, 0);
    const buf = await (await dst.convertToBlob({ type: "image/png" })).arrayBuffer();
    (self as unknown as Worker).postMessage({ id, ok: true, buf }, [buf]);
  } catch (err) {
    (self as unknown as Worker).postMessage({ id, ok: false, error: String(err) });
  }
};
