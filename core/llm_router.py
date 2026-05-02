from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from core.rate_limiter import has_headroom


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


_CIRCUIT_LOCK = threading.RLock()
_CIRCUIT_STATE: dict[str, dict[str, float | int | str]] = {}


def _now() -> float:
    return time.time()


def _provider_priority() -> list[str]:
    configured = os.getenv("PROVIDER_PRIORITY", "groq,gemini,ollama")
    return [p.strip().lower() for p in configured.split(",") if p.strip()]


def _provider_env(provider: str) -> tuple[str, str]:
    if provider == "groq":
        return ("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY", ""))
    if provider == "gemini":
        return ("https://generativelanguage.googleapis.com/v1beta/openai/", os.getenv("GEMINI_API_KEY", ""))
    if provider == "ollama":
        return (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), os.getenv("OLLAMA_API_KEY", "ollama"))
    return ("", "")


def _provider_model(provider: str, requested_model: str) -> str:
    model = (requested_model or "").strip()
    if provider == "gemini":
        if model.startswith("llama") or model.startswith("meta-llama"):
            return os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
    if provider == "ollama":
        return os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.1:8b")
    return model or "llama-3.1-8b-instant"


def _is_provider_open(provider: str) -> bool:
    with _CIRCUIT_LOCK:
        row = _CIRCUIT_STATE.get(provider)
        if not row:
            return False
        return row.get("state", "CLOSED") == "OPEN" and float(row.get("until_ts", 0.0)) > _now()


def note_provider_failure(provider: str) -> None:
    with _CIRCUIT_LOCK:
        row = _CIRCUIT_STATE.setdefault(provider, {"fails": 0, "window_start": _now(), "state": "CLOSED", "until_ts": 0.0})
        window_start = float(row.get("window_start", _now()))
        now = _now()
        if now - window_start > 60:
            row["window_start"] = now
            row["fails"] = 0
        row["fails"] = int(row.get("fails", 0)) + 1
        if int(row["fails"]) >= 3:
            row["state"] = "OPEN"
            row["until_ts"] = now + 300


def note_provider_success(provider: str) -> None:
    with _CIRCUIT_LOCK:
        _CIRCUIT_STATE[provider] = {"fails": 0, "window_start": _now(), "state": "CLOSED", "until_ts": 0.0}


def get_circuit_status() -> dict[str, str]:
    result: dict[str, str] = {}
    now = _now()
    with _CIRCUIT_LOCK:
        for provider in _provider_priority():
            row = _CIRCUIT_STATE.get(provider, {"state": "CLOSED", "until_ts": 0.0})
            state = str(row.get("state", "CLOSED"))
            until_ts = float(row.get("until_ts", 0.0))
            if state == "OPEN" and until_ts <= now:
                state = "HALF_OPEN"
            result[provider] = state
    return result


def select_provider(requested_model: str) -> ProviderConfig:
    minute_limit = int(os.getenv("MODEL_MINUTE_LIMIT_TOKENS", "250000"))
    day_limit = int(os.getenv("MODEL_DAY_LIMIT_TOKENS", "4000000"))
    for provider in _provider_priority():
        if _is_provider_open(provider):
            continue
        base_url, api_key = _provider_env(provider)
        if not base_url or not api_key:
            continue
        model = _provider_model(provider, requested_model)
        headroom = has_headroom(model=model, minute_limit_tokens=minute_limit, day_limit_tokens=day_limit, expected_tokens=800)
        if not headroom.allowed:
            continue
        return ProviderConfig(name=provider, base_url=base_url, api_key=api_key, model=model)

    return ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY", ""),
        model=requested_model or "llama-3.1-8b-instant",
    )

