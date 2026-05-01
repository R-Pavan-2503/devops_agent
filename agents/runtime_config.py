import copy
import os
import threading
import time
from typing import Any

import httpx


AGENT_SETTINGS_TEMPLATE: dict[str, dict[str, Any]] = {
    "architecture": {
        "display_name": "Architecture Agent",
        "size_class": "large",
        "model": "llama-3.3-70b-versatile",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 3000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "backend": {
        "display_name": "Backend Analyst",
        "size_class": "large",
        "model": "llama-3.3-70b-versatile",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "security": {
        "display_name": "Security Agent",
        "size_class": "small",
        "model": "llama-3.1-8b-instant",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "code_quality": {
        "display_name": "Code Quality Agent",
        "size_class": "small",
        "model": "llama-3.1-8b-instant",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "qa": {
        "display_name": "QA / SDET Agent",
        "size_class": "small",
        "model": "llama-3.1-8b-instant",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "frontend": {
        "display_name": "Frontend Integration Agent",
        "size_class": "small",
        "model": "llama-3.1-8b-instant",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "critique_resolve": {
        "display_name": "Critique Resolve Agent",
        "size_class": "large",
        "model": "llama-3.3-70b-versatile",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 3000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "development": {
        "display_name": "Developer Agent",
        "size_class": "large",
        "model": "llama-3.3-70b-versatile",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 3000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "documentation": {
        "display_name": "Documentation Agent",
        "size_class": "large",
        "model": "llama-3.3-70b-versatile",
        "parameters": {
            "temperature": 0.2,
            "max_tokens": 3000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
    "wiki_builder": {
        "display_name": "Wiki Builder Agent",
        "size_class": "large",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "parameters": {
            "temperature": 0.3,
            "max_tokens": 4000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    },
}

SIZE_CLASS_MODELS: dict[str, list[str]] = {
    "small": [
        "llama-3.1-8b-instant",
        "llama3-8b-8192",
        "gemma2-9b-it",
        "mixtral-8x7b-32768",
    ],
    "large": [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama3-70b-8192",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],
}

# Estimated $ per 1M tokens from current Groq model cards; used only for UI estimate.
MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.11, "output": 0.34},
}

_lock = threading.RLock()
_session_settings: dict[str, dict[str, Any]] = copy.deepcopy(AGENT_SETTINGS_TEMPLATE)
_usage_by_model: dict[str, dict[str, float]] = {}
_usage_events: list[dict[str, Any]] = []
_rate_limit_cache: dict[str, Any] = {
    "checked_at": "",
    "status": "unavailable",
    "message": "Not checked yet.",
    "limit_tokens": 0,
    "remaining_tokens": 0,
    "used_tokens_window": 0,
    "reset_tokens": "",
    "limit_requests": 0,
    "remaining_requests": 0,
    "used_requests_window": 0,
    "reset_requests": "",
}
_rate_limit_cache_ts = 0.0


def _to_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _to_int_header(value: Any) -> int:
    if value is None:
        return 0
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            return 0


def _estimate_credits(model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> float:
    pricing = MODEL_PRICING_PER_1M.get(model)
    if not pricing:
        return round(total_tokens / 1_000_000, 6)
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


def get_defaults() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(AGENT_SETTINGS_TEMPLATE)


def reset_session() -> None:
    global _session_settings, _usage_by_model, _usage_events
    with _lock:
        _session_settings = copy.deepcopy(AGENT_SETTINGS_TEMPLATE)
        _usage_by_model = {}
        _usage_events = []


def get_session_settings() -> dict[str, dict[str, Any]]:
    with _lock:
        return copy.deepcopy(_session_settings)


def apply_session_settings(new_settings: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """
    Merge incoming settings into in-memory runtime settings.
    Unknown agents/fields are ignored for safety.
    """
    global _session_settings
    with _lock:
        merged = copy.deepcopy(_session_settings)
        if not isinstance(new_settings, dict):
            return merged

        for agent_key, incoming in new_settings.items():
            if agent_key not in merged or not isinstance(incoming, dict):
                continue

            base = merged[agent_key]
            current_model = str(base.get("model", ""))
            size_class = str(base.get("size_class", "small"))
            allowed_models = set(SIZE_CLASS_MODELS.get(size_class, []))

            requested_model = str(incoming.get("model", current_model)).strip()
            if requested_model and (requested_model in allowed_models or requested_model == current_model):
                base["model"] = requested_model

            incoming_params = incoming.get("parameters", {})
            if isinstance(incoming_params, dict):
                params = base.setdefault("parameters", {})
                for param_key, param_value in incoming_params.items():
                    if param_key == "temperature":
                        params[param_key] = _to_float(param_value, _to_float(params.get(param_key), 0.2))
                    elif param_key == "top_p":
                        params[param_key] = _to_float(param_value, _to_float(params.get(param_key), 1.0))
                    elif param_key == "max_tokens":
                        params[param_key] = _to_int(param_value, _to_int(params.get(param_key), 300))
                    elif param_key in ("frequency_penalty", "presence_penalty"):
                        params[param_key] = _to_float(param_value, _to_float(params.get(param_key), 0.0))
                    else:
                        params[param_key] = param_value

        _session_settings = merged
        return copy.deepcopy(_session_settings)


def build_model_catalog() -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "")
    available_ids: set[str] = set()
    availability_error = ""

    if api_key:
        try:
            response = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=6.0,
            )
            response.raise_for_status()
            payload = response.json()
            for model in payload.get("data", []):
                model_id = model.get("id")
                if isinstance(model_id, str):
                    available_ids.add(model_id)
        except Exception as exc:
            availability_error = str(exc)
    else:
        availability_error = "GROQ_API_KEY is not configured."

    catalog: dict[str, list[dict[str, Any]]] = {"small": [], "large": []}
    defaults = get_defaults()
    with _lock:
        current = copy.deepcopy(_session_settings)

    for size_class, model_ids in SIZE_CLASS_MODELS.items():
        for model_id in model_ids:
            is_default_model = any(
                current.get(agent_key, {}).get("model") == model_id
                or defaults.get(agent_key, {}).get("model") == model_id
                for agent_key in defaults.keys()
            )
            is_available = (model_id in available_ids) if available_ids else is_default_model
            catalog[size_class].append(
                {
                    "id": model_id,
                    "available": is_available,
                    "unavailable_reason": "" if is_available else "Unavailable for current Groq key",
                }
            )

    return {"models_by_size": catalog, "availability_error": availability_error}


def record_usage_from_response(model: str, response_obj: Any) -> None:
    usage = getattr(response_obj, "usage_metadata", None) or {}
    prompt_tokens = int(usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return

    credits = _estimate_credits(model, prompt_tokens, completion_tokens, total_tokens)
    with _lock:
        current = _usage_by_model.get(
            model,
            {
                "tokens_used": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_credits": 0.0,
            },
        )
        current["tokens_used"] += total_tokens
        current["prompt_tokens"] += prompt_tokens
        current["completion_tokens"] += completion_tokens
        current["estimated_credits"] = round(current["estimated_credits"] + credits, 6)
        _usage_by_model[model] = current
        _usage_events.append(
            {
                "ts": time.time(),
                "model": model,
                "tokens": total_tokens,
            }
        )
        # Keep only recent events to bound memory.
        cutoff = time.time() - 3600
        if len(_usage_events) > 5000:
            _usage_events[:] = [evt for evt in _usage_events if float(evt.get("ts", 0)) >= cutoff]


def get_usage_summary() -> dict[str, Any]:
    with _lock:
        by_model = copy.deepcopy(_usage_by_model)
        events = list(_usage_events)

    usage_rows = []
    total_tokens = 0
    total_credits = 0.0
    for model_name, stats in by_model.items():
        tokens_used = int(stats.get("tokens_used", 0))
        credits = float(stats.get("estimated_credits", 0.0))
        total_tokens += tokens_used
        total_credits += credits
        usage_rows.append(
            {
                "model": model_name,
                "tokens_used": tokens_used,
                "estimated_credits": round(credits, 6),
            }
        )

    usage_rows.sort(key=lambda item: item["tokens_used"], reverse=True)
    now = time.time()
    cutoff_60 = now - 60
    tokens_last_60s = 0
    reqs_last_60s = 0
    per_model_60s: dict[str, int] = {}
    for event in events:
        ts = float(event.get("ts", 0))
        if ts < cutoff_60:
            continue
        reqs_last_60s += 1
        tok = int(event.get("tokens", 0))
        model = str(event.get("model", "unknown"))
        tokens_last_60s += tok
        per_model_60s[model] = per_model_60s.get(model, 0) + tok

    return {
        "by_model": usage_rows,
        "total": {
            "tokens_used": total_tokens,
            "estimated_credits": round(total_credits, 6),
        },
        "rolling": {
            "window_seconds": 60,
            "tokens_last_window": tokens_last_60s,
            "requests_last_window": reqs_last_60s,
            "tokens_per_model_last_window": per_model_60s,
        },
    }


def get_live_rate_limits(force_refresh: bool = False, min_cache_seconds: int = 6) -> dict[str, Any]:
    """
    Best-effort rate limit snapshot from Groq response headers.
    Uses a tiny chat completion probe so token headers are populated.
    """
    global _rate_limit_cache_ts, _rate_limit_cache
    now = time.time()
    with _lock:
        if not force_refresh and (now - _rate_limit_cache_ts) < min_cache_seconds:
            return copy.deepcopy(_rate_limit_cache)

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        snapshot = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "unavailable",
            "message": "GROQ_API_KEY is not configured.",
            "limit_tokens": 0,
            "remaining_tokens": 0,
            "used_tokens_window": 0,
            "reset_tokens": "",
            "limit_requests": 0,
            "remaining_requests": 0,
            "used_requests_window": 0,
            "reset_requests": "",
        }
        with _lock:
            _rate_limit_cache = snapshot
            _rate_limit_cache_ts = now
        return copy.deepcopy(snapshot)

    try:
        probe_model = get_session_settings().get("security", {}).get("model", "llama-3.1-8b-instant")
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": probe_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            },
            timeout=6.0,
        )
        response.raise_for_status()
        headers = response.headers
        limit_tokens = _to_int_header(headers.get("x-ratelimit-limit-tokens"))
        remaining_tokens = _to_int_header(headers.get("x-ratelimit-remaining-tokens"))
        limit_requests = _to_int_header(headers.get("x-ratelimit-limit-requests"))
        remaining_requests = _to_int_header(headers.get("x-ratelimit-remaining-requests"))

        used_tokens_window = max(limit_tokens - remaining_tokens, 0) if limit_tokens else 0
        used_requests_window = max(limit_requests - remaining_requests, 0) if limit_requests else 0

        snapshot = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "ok",
            "message": "",
            "limit_tokens": limit_tokens,
            "remaining_tokens": remaining_tokens,
            "used_tokens_window": used_tokens_window,
            "reset_tokens": str(headers.get("x-ratelimit-reset-tokens", "")),
            "limit_requests": limit_requests,
            "remaining_requests": remaining_requests,
            "used_requests_window": used_requests_window,
            "reset_requests": str(headers.get("x-ratelimit-reset-requests", "")),
        }
    except Exception as exc:
        snapshot = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "unavailable",
            "message": str(exc),
            "limit_tokens": 0,
            "remaining_tokens": 0,
            "used_tokens_window": 0,
            "reset_tokens": "",
            "limit_requests": 0,
            "remaining_requests": 0,
            "used_requests_window": 0,
            "reset_requests": "",
        }

    with _lock:
        _rate_limit_cache = snapshot
        _rate_limit_cache_ts = now
    return copy.deepcopy(snapshot)
