"""Minimal Ollama client. The app must work without Ollama installed, so every
call degrades quietly: availability is probed, errors return None."""
from __future__ import annotations
import httpx


def list_models(base_url: str) -> list[str]:
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def is_available(base_url: str) -> bool:
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def generate(base_url: str, model: str, prompt: str, system: str = "") -> str | None:
    try:
        r = httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "system": system, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response")
    except Exception:  # noqa: BLE001
        return None
