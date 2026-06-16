// EPA AQI category colors + NAC avalanche danger colors (canonical scales).
export interface AqiBand { max: number; color: string; label: string; }

export const AQI_BANDS: AqiBand[] = [
  { max: 50, color: "#00e400", label: "Good" },
  { max: 100, color: "#ffff00", label: "Moderate" },
  { max: 150, color: "#ff7e00", label: "Unhealthy for Sensitive Groups" },
  { max: 200, color: "#ff0000", label: "Unhealthy" },
  { max: 300, color: "#8f3f97", label: "Very Unhealthy" },
  { max: Infinity, color: "#7e0023", label: "Hazardous" },
];

export function aqiColor(aqi: number): string {
  return (AQI_BANDS.find((b) => aqi <= b.max) ?? AQI_BANDS[AQI_BANDS.length - 1]).color;
}
export function aqiCategory(aqi: number): string {
  return (AQI_BANDS.find((x) => aqi <= x.max) ?? AQI_BANDS[AQI_BANDS.length - 1]).label;
}

export const AVY_DANGER: Record<string, string> = {
  "1": "#52ba4a", low: "#52ba4a",
  "2": "#fff300", moderate: "#fff300",
  "3": "#f7941e", considerable: "#f7941e",
  "4": "#ed1c24", high: "#ed1c24",
  "5": "#231f20", extreme: "#231f20",
};

export function avyColor(level: string | number): string {
  return AVY_DANGER[String(level).toLowerCase().trim()] ?? "#9aa395";
}
