from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetCheck:
    allowed: bool
    reason: str
    used_last_minute: int
    used_today: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events = defaultdict(deque)  # model -> deque[(ts, tokens)]
        self._events_day = defaultdict(deque)

    def register_usage(self, model: str, tokens: int) -> None:
        now = time.time()
        with self._lock:
            self._events[model].append((now, int(tokens)))
            self._events_day[model].append((now, int(tokens)))
            self._trim_locked(model)

    def _trim_locked(self, model: str) -> None:
        now = time.time()
        min_cutoff = now - 60
        day_cutoff = now - 86400
        while self._events[model] and self._events[model][0][0] < min_cutoff:
            self._events[model].popleft()
        while self._events_day[model] and self._events_day[model][0][0] < day_cutoff:
            self._events_day[model].popleft()

    def check_budget(
        self,
        model: str,
        minute_limit_tokens: int,
        day_limit_tokens: int,
        expected_tokens: int,
    ) -> BudgetCheck:
        with self._lock:
            self._trim_locked(model)
            used_minute = sum(tok for _, tok in self._events[model])
            used_day = sum(tok for _, tok in self._events_day[model])

        if used_minute + expected_tokens > minute_limit_tokens:
            return BudgetCheck(False, "minute budget exceeded", used_minute, used_day)
        if used_day + expected_tokens > day_limit_tokens:
            return BudgetCheck(False, "daily budget exceeded", used_minute, used_day)
        return BudgetCheck(True, "ok", used_minute, used_day)


_RATE_LIMITER = InMemoryRateLimiter()


def register_usage(model: str, tokens: int) -> None:
    _RATE_LIMITER.register_usage(model, tokens)


def has_headroom(model: str, minute_limit_tokens: int, day_limit_tokens: int, expected_tokens: int = 600) -> BudgetCheck:
    return _RATE_LIMITER.check_budget(model, minute_limit_tokens, day_limit_tokens, expected_tokens)

