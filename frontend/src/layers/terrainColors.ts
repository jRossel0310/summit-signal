// Single source of truth for slope/aspect coloring — used by BOTH the worker
// (pixel shading) and the legends (so they can never drift apart).

export interface SlopeBucket { min: number; max: number | null; color: string; label: string; }

export const SLOPE_BUCKETS: SlopeBucket[] = [
  { min: 0, max: 15, color: "#1a9850", label: "0–15°" },
  { min: 15, max: 25, color: "#a6d96a", label: "15–25°" },
  { min: 25, max: 30, color: "#f1e34d", label: "25–30°" },
  { min: 30, max: 35, color: "#fdae61", label: "30–35°" },
  { min: 35, max: 45, color: "#d73027", label: "35–45°" },
  { min: 45, max: null, color: "#7b3294", label: "45°+" },
];

export type Direction = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

export const ASPECT_COLORS: Record<Direction, string> = {
  N: "#3b6fb3", NE: "#3aa6b0", E: "#5bb86a", SE: "#bcc94a",
  S: "#e8b53a", SW: "#e07a3a", W: "#b3506f", NW: "#6b5b95",
};

const DIRECTIONS: Direction[] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

export function slopeColor(deg: number): string {
  for (const b of SLOPE_BUCKETS) {
    if (deg >= b.min && (b.max === null || deg < b.max)) return b.color;
  }
  return SLOPE_BUCKETS[SLOPE_BUCKETS.length - 1].color;
}

export function aspectColor(deg: number): string {
  const idx = Math.round(((deg % 360) + 360) % 360 / 45) % 8;
  return ASPECT_COLORS[DIRECTIONS[idx]];
}
