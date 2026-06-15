// Pure terrain math, mirrored by the backend slope_aspect.py (the FE drives the
// map shading; the BE the dashboard value). Kept in sync by their unit tests.

export function decodeTerrarium(r: number, g: number, b: number): number {
  return r * 256 + g + b / 256 - 32768;
}

export function decodeMapbox(r: number, g: number, b: number): number {
  return -10000 + (r * 65536 + g * 256 + b) * 0.1;
}

/** slope (deg) + aspect (deg, 0=N 90=E clockwise) from 5 elevations + spacing (m). */
export function pixelSlopeAspect(
  center: number, north: number, east: number, south: number, west: number, spacing: number,
): { slope: number; aspect: number } {
  void center;
  const dzdx = (east - west) / (2 * spacing);
  const dzdy = (north - south) / (2 * spacing);
  const slope = (Math.atan(Math.hypot(dzdx, dzdy)) * 180) / Math.PI;
  if (dzdx === 0 && dzdy === 0) return { slope: 0, aspect: 0 };
  const aspect = ((Math.atan2(-dzdx, -dzdy) * 180) / Math.PI + 360) % 360;
  return { slope, aspect };
}

/** Web-mercator ground resolution (m/px) at a latitude + zoom for 256px tiles. */
export function metersPerPixel(latDeg: number, zoom: number): number {
  return (40075016.686 * Math.cos((latDeg * Math.PI) / 180)) / (256 * 2 ** zoom);
}

/** Latitude (deg) of the center of tile y at zoom z. */
export function tileCenterLat(y: number, z: number): number {
  const n = Math.PI - (2 * Math.PI * (y + 0.5)) / 2 ** z;
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}
