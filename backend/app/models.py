"""SQLAlchemy models. One class per table required by the SummitSignal spec."""
import datetime as dt
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship
from .database import Base


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


class Trip(Base):
    __tablename__ = "trips"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    location_name = Column(String, default="")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    start_date = Column(String, nullable=False)   # ISO date
    end_date = Column(String, nullable=False)     # ISO date
    trip_type = Column(String, default="general") # general | backpacking | mountaineering
    notes = Column(Text, default="")
    elevation_bands = Column(Text, nullable=True)  # JSON: {"trailhead_ft":..,"mid_ft":..,"high_ft":..}
    gpx_route_id = Column(Integer, ForeignKey("gpx_routes.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    last_checked_at = Column(DateTime, nullable=True)
    latest_concern_status = Column(String, nullable=True)

    gpx_route = relationship("GpxRoute", foreign_keys=[gpx_route_id])
    condition_checks = relationship(
        "ConditionCheck", back_populates="trip", cascade="all, delete-orphan"
    )
    saved_reports = relationship(
        "SavedReport", cascade="all, delete-orphan"
    )


class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    kind = Column(String, default="")        # peak, trailhead, park, coordinate ...
    source = Column(String, default="")      # nominatim, manual
    created_at = Column(DateTime, default=utcnow)


class GpxRoute(Base):
    __tablename__ = "gpx_routes"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, nullable=True)
    filename = Column(String, default="route.gpx")
    points_json = Column(Text, default="[]")   # [[lat, lon, ele?], ...] (simplified)
    bbox_json = Column(Text, nullable=True)    # {"west":..,"south":..,"east":..,"north":..}
    length_miles = Column(Float, nullable=True)
    min_elevation_ft = Column(Float, nullable=True)
    max_elevation_ft = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class ConditionCheck(Base):
    __tablename__ = "condition_checks"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running | complete | failed
    overall_concern_status = Column(String, nullable=True)
    data_completeness_score = Column(Float, nullable=True)  # 0..1
    summary_text = Column(Text, nullable=True)

    trip = relationship("Trip", back_populates="condition_checks")
    connector_results = relationship(
        "ConnectorResult", back_populates="condition_check", cascade="all, delete-orphan"
    )
    risk_flags = relationship(
        "RiskFlag", back_populates="condition_check", cascade="all, delete-orphan"
    )
    ai_summaries = relationship(
        "AiSummary", back_populates="condition_check", cascade="all, delete-orphan"
    )


class ConnectorResult(Base):
    __tablename__ = "connector_results"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
    connector_name = Column(String, nullable=False)
    status = Column(String, default="skipped")  # success | partial | failed | skipped
    source_name = Column(String, default="")
    source_url = Column(String, default="")
    source_timestamp = Column(String, nullable=True)  # as reported by the source
    retrieved_at = Column(DateTime, default=utcnow)
    raw_json = Column(Text, nullable=True)
    normalized_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    condition_check = relationship("ConditionCheck", back_populates="connector_results")


class RiskFlag(Base):
    __tablename__ = "risk_flags"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
    severity = Column(String, default="info")   # info | moderate | major | unknown
    category = Column(String, default="weather")
    # weather | fire | smoke | official_alert | avalanche | snow | access | data_gap
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    source_connector = Column(String, default="")
    source_url = Column(String, default="")
    confidence = Column(String, default="medium")  # low | medium | high

    condition_check = relationship("ConditionCheck", back_populates="risk_flags")


class AiSummary(Base):
    __tablename__ = "ai_summaries"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
    generator = Column(String, default="rule_based")  # rule_based | ollama:<model>
    summary_markdown = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    condition_check = relationship("ConditionCheck", back_populates="ai_summaries")


class SavedReport(Base):
    __tablename__ = "saved_reports"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    condition_check_id = Column(
        Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=True)
    html = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")


class ApiKey(Base):
    __tablename__ = "api_keys"
    name = Column(String, primary_key=True)  # firms, airnow, nps
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
