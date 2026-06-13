// Types mirroring the FastAPI backend schemas.

export interface User {
  id: number;
  email: string;
}

export type TripType = "general" | "backpacking" | "mountaineering";

export interface ElevationBands {
  trailhead_ft?: number | null;
  mid_ft?: number | null;
  high_ft?: number | null;
}

export interface GpxRouteOut {
  id: number;
  filename: string;
  length_miles: number | null;
  min_elevation_ft: number | null;
  max_elevation_ft: number | null;
  bbox: number[] | null; // [minLon, minLat, maxLon, maxLat]
  points: [number, number, number | null][]; // [lat, lon, ele_ft]
}

export interface Trip {
  id: number;
  name: string;
  location_name: string | null;
  latitude: number;
  longitude: number;
  start_date: string;
  end_date: string;
  trip_type: TripType;
  notes: string | null;
  elevation_bands: ElevationBands | null;
  gpx_route_id: number | null;
  gpx_route?: GpxRouteOut | null;
  created_at: string;
  updated_at: string;
  last_checked_at: string | null;
  latest_concern_status: string | null;
}

export interface TripCreate {
  name: string;
  location_name?: string | null;
  latitude: number;
  longitude: number;
  start_date: string;
  end_date: string;
  trip_type: TripType;
  notes?: string | null;
  elevation_bands?: ElevationBands | null;
}

export type ConnectorStatus = "success" | "partial" | "failed" | "skipped";

export interface ConnectorResult {
  id: number;
  connector_name: string;
  status: ConnectorStatus;
  source_name: string | null;
  source_url: string | null;
  source_timestamp: string | null;
  retrieved_at: string | null;
  normalized: Record<string, unknown> | null;
  error_message: string | null;
}

export type Severity = "info" | "moderate" | "major" | "unknown";

export interface RiskFlag {
  id: number;
  severity: Severity;
  category: string;
  title: string;
  description: string | null;
  source_connector: string | null;
  source_url: string | null;
  confidence: string | null;
}

export interface AiSummary {
  summary_text: string;
  generator: string;
  created_at?: string;
}

export interface ConditionCheck {
  id: number;
  trip_id: number;
  started_at: string;
  completed_at: string | null;
  status: "running" | "complete" | "failed";
  overall_concern_status: string | null;
  data_completeness_score: number | null;
  summary_text: string | null;
}

export interface ConditionCheckDetail extends ConditionCheck {
  connector_results: ConnectorResult[];
  risk_flags: RiskFlag[];
  ai_summary: AiSummary | null;
}

export interface CheckStatus {
  id: number;
  status: "running" | "complete" | "failed";
  connectors_completed: number;
  connectors_total: number;
  current_connector: string | null;
  overall_concern_status: string | null;
}

export interface SearchResult {
  display_name: string;
  latitude: number;
  longitude: number;
  kind: string | null;
}

export interface AppSettings {
  fire_radius_miles: number;
  aqi_moderate_threshold: number;
  aqi_major_threshold: number;
  wind_gust_moderate_mph: number;
  wind_gust_major_mph: number;
  precip_prob_moderate: number;
  cold_low_f: number;
  stale_hours: number;
  connectors_enabled: Record<string, boolean>;
  api_keys_present: Record<string, boolean>;
}

export interface SettingsUpdate extends Partial<Omit<AppSettings, "api_keys_present">> {}

export const CONNECTOR_LABELS: Record<string, string> = {
  nws_weather: "NWS Weather",
  usgs_elevation: "USGS Elevation",
  elevation_adjusted: "Elevation-Adjusted Weather",
  nasa_firms: "NASA FIRMS Fires",
  nifc_wfigs: "Fire Perimeters (WFIGS)",
  airnow: "AirNow Air Quality",
  nps_alerts: "NPS Alerts",
  avalanche: "Avalanche Region",
  weather_discussion: "Forecast Discussion (AFD)",
};

export const TRIP_TYPE_LABELS: Record<TripType, string> = {
  general: "General trailhead",
  backpacking: "Backpacking",
  mountaineering: "Mountaineering / glacier",
};
