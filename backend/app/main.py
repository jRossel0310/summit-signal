"""SummitSignal backend entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Creates the schema on startup. There is no global seeding: sample trips are
seeded per user at signup. CORS origins come from ALLOWED_ORIGINS."""
from __future__ import annotations
import datetime as dt
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - registers tables
from .database import Base, engine
from .routes import auth as auth_routes
from .routes import trips as trips_routes
from .routes import checks as checks_routes
from .routes import misc as misc_routes
from .routes import map as map_routes

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or DEFAULT_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SummitSignal", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "SummitSignal", "time": dt.datetime.now(dt.timezone.utc)}


app.include_router(auth_routes.router)
app.include_router(trips_routes.router)
app.include_router(checks_routes.router)
app.include_router(misc_routes.router)
app.include_router(map_routes.router)
