"""Pydantic schemas: typed request/response bodies and connector result envelope."""
from __future__ import annotations
import datetime as dt
from typing import Any, Optional
from pydantic import BaseModel, Field

CONCERN_STATUSES = [
    "No major concerns found",
    "Some concerns found",
    "Major concerns found",
    "Data incomplete",
    "Source check failed",
]


# ---------- Connector envelope (shared by all connectors) ----------

class ConnectorOutput(BaseModel):
    """Normalized envelope every connector returns."""
    connector_name: str
    status: str = "skipped"  # success | partial | failed | skipped
    source_name: str = ""
    source_url: str = ""
    source_timestamp: Optional[str] = None
    raw: Any = None
    normalized: Any = None
    error_message: Optional[str] = None


# ---------- Auth ----------

class SignupRequest(BaseModel):
    email: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut


# ---------- Trips ----------

class ElevationBands(BaseModel):
    trailhead_ft: Optional[float] = None
    mid_ft: Optional[float] = None
    high_ft: Optional[float] = None


class TripCreate(BaseModel):
    name: str
    # Optional: the web client sends null for an unnamed map point / empty notes.
    # create_trip coerces null -> "" so the stored values stay plain strings.
    location_name: Optional[str] = ""
    latitude: float
    longitude: float
    start_date: str
    end_date: str
    trip_type: str = "general"  # general | backpacking | mountaineering
    notes: Optional[str] = ""
    elevation_bands: Optional[ElevationBands] = None


class TripUpdate(BaseModel):
    name: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    trip_type: Optional[str] = None
    notes: Optional[str] = None
    elevation_bands: Optional[ElevationBands] = None


class GpxRouteOut(BaseModel):
    id: int
    filename: str
    points: list
    bbox: Optional[dict] = None
    length_miles: Optional[float] = None
    min_elevation_ft: Optional[float] = None
    max_elevation_ft: Optional[float] = None


class TripOut(BaseModel):
    id: int
    name: str
    location_name: str
    latitude: float
    longitude: float
    start_date: str
    end_date: str
    trip_type: str
    notes: str
    elevation_bands: Optional[dict] = None
    gpx_route_id: Optional[int] = None
    gpx_route: Optional[GpxRouteOut] = None
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    last_checked_at: Optional[dt.datetime] = None
    latest_concern_status: Optional[str] = None


# ---------- Route builder ----------

class RouteWaypoint(BaseModel):
    lat: float
    lon: float


class RouteSnapOptions(BaseModel):
    preferTrails: bool = True
    avoidRoads: bool = True


class RouteSnapRequest(BaseModel):
    waypoints: list[RouteWaypoint] = Field(default_factory=list)
    profile: str = "hiking"  # hiking | walking
    options: Optional[RouteSnapOptions] = None


class RouteSnapResponse(BaseModel):
    status: str  # success | partial | failed | unavailable
    message: Optional[str] = None
    provider: str
    profile: str
    points: list = Field(default_factory=list)        # [[lat, lon, ele_or_null], ...]
    geojson: Any = None                               # FeatureCollection or Feature
    length_miles: Optional[float] = None
    bbox: Optional[list] = None                       # [minLon, minLat, maxLon, maxLat]
    metadata: dict = Field(default_factory=dict)
    segments: list = Field(default_factory=list)      # [{from,to,provider,snapped,length_miles}]


class BuiltRouteSaveRequest(BaseModel):
    name: str = "Built route"
    points: list = Field(default_factory=list)        # [[lat, lon, ele_or_null], ...]
    bbox: Optional[list] = None                       # [minLon, minLat, maxLon, maxLat]
    length_miles: Optional[float] = None
    source: str = "manual"                            # manual | openrouteservice
    profile: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# ---------- Condition checks ----------

class RiskFlagOut(BaseModel):
    id: int
    severity: str
    category: str
    title: str
    description: str
    source_connector: str
    source_url: str
    confidence: str


class ConnectorResultOut(BaseModel):
    id: int
    connector_name: str
    status: str
    source_name: str
    source_url: str
    source_timestamp: Optional[str]
    retrieved_at: Optional[dt.datetime]
    normalized: Any = None
    error_message: Optional[str] = None


class ConditionCheckOut(BaseModel):
    id: int
    trip_id: int
    started_at: Optional[dt.datetime]
    completed_at: Optional[dt.datetime]
    status: str
    overall_concern_status: Optional[str]
    data_completeness_score: Optional[float]
    summary_text: Optional[str]


class AiSummaryOut(BaseModel):
    summary_text: str
    generator: str
    created_at: Optional[dt.datetime] = None


class ConditionCheckDetail(ConditionCheckOut):
    connector_results: list[ConnectorResultOut] = Field(default_factory=list)
    risk_flags: list[RiskFlagOut] = Field(default_factory=list)
    ai_summary: Optional[AiSummaryOut] = None


# ---------- Search ----------

class LocationSearchRequest(BaseModel):
    query: str


class LocationSearchResult(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    kind: str = ""
    source: str = ""


class LocationSearchResponse(BaseModel):
    results: list[LocationSearchResult] = Field(default_factory=list)


# ---------- Settings ----------

class SettingsOut(BaseModel):
    fire_radius_miles: float = 30.0
    aqi_moderate_threshold: int = 101   # AQI >= this -> moderate (USG)
    aqi_major_threshold: int = 151      # AQI >= this -> major (Unhealthy+)
    wind_gust_moderate_mph: float = 30.0
    wind_gust_major_mph: float = 50.0
    precip_prob_moderate: float = 60.0
    cold_low_f: float = 10.0
    stale_hours: float = 24.0
    connectors_enabled: dict = Field(default_factory=dict)
    api_keys_present: dict = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    fire_radius_miles: Optional[float] = None
    aqi_moderate_threshold: Optional[int] = None
    aqi_major_threshold: Optional[int] = None
    wind_gust_moderate_mph: Optional[float] = None
    wind_gust_major_mph: Optional[float] = None
    precip_prob_moderate: Optional[float] = None
    cold_low_f: Optional[float] = None
    stale_hours: Optional[float] = None
    connectors_enabled: Optional[dict] = None


# ---------- Map point-context ----------

class PointSectionOut(BaseModel):
    layer_id: str
    title: str
    status: str
    data: Optional[dict] = None
    message: Optional[str] = None
    source: Optional[dict] = None


class PointContextResponse(BaseModel):
    lat: float
    lon: float
    place_name: Optional[str] = None
    sections: list[PointSectionOut] = Field(default_factory=list)


class LayerDataResponse(BaseModel):
    status: str
    features: list[dict] = Field(default_factory=list)
    message: Optional[str] = None
