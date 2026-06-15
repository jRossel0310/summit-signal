"""Map point-context providers: shared types + result factories.

A Provider answers "what is true at this lat/lon for one layer?" Providers are
isolated like connectors: they never touch the DB and never raise; failures come
back as status="error". Status values map 1:1 onto the frontend SectionStatus
(snake_case here -> kebab-case at the route boundary)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class ProviderContext:
    latitude: float
    longitude: float
    bbox: Optional[dict] = None          # reserved for future route-based analysis
    settings: dict = field(default_factory=dict)
    shared: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    provider_id: str
    status: str                          # ok | empty | needs_key | error | coming_soon
    title: str
    data: Optional[dict] = None
    message: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_timestamp: Optional[str] = None


class Provider(Protocol):
    id: str
    title: str
    requires_key: Optional[str]
    always_on: bool
    def fetch(self, ctx: ProviderContext) -> ProviderResult: ...


def ok(pid, title, data, source_name=None, source_url=None, source_timestamp=None):
    return ProviderResult(pid, "ok", title, data=data, source_name=source_name,
                          source_url=source_url, source_timestamp=source_timestamp)


def empty(pid, title, message):
    return ProviderResult(pid, "empty", title, message=message)


def needs_key(pid, title, env_var):
    return ProviderResult(pid, "needs_key", title,
                          message=f"Set {env_var} on the server to enable this layer.")


def error(pid, title, message):
    return ProviderResult(pid, "error", title, message=str(message)[:500])


def coming_soon(pid, title, phase):
    return ProviderResult(pid, "coming_soon", title, message=f"Arrives in Phase {phase}.")
