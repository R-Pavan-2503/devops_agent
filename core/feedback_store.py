from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT


_DB_PATH = PROJECT_ROOT / "feedback.db"
_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_feedback_store() -> None:
    with _LOCK:
        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS verdicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER,
                    repo TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    vote TEXT NOT NULL,
                    critique_text TEXT,
                    file_path TEXT,
                    line_number INTEGER,
                    severity TEXT,
                    confidence REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    verdict_id INTEGER NOT NULL,
                    corrected_by TEXT,
                    correction TEXT NOT NULL,
                    note TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (verdict_id) REFERENCES verdicts(id)
                );

                CREATE TABLE IF NOT EXISTS coverage_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER,
                    repo TEXT NOT NULL,
                    coverage_score REAL NOT NULL,
                    quality_label TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()


def save_verdict(
    pr_number: int,
    repo: str,
    agent_name: str,
    vote: str,
    critique_text: str,
    file_path: str = "",
    line_number: int | None = None,
    severity: str = "",
    confidence: float = 0.0,
) -> int:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO verdicts (
                    pr_number, repo, agent_name, vote, critique_text,
                    file_path, line_number, severity, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pr_number,
                    repo or "unknown",
                    agent_name,
                    vote,
                    critique_text,
                    file_path,
                    line_number,
                    severity,
                    float(confidence),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)


def get_agent_history(agent_name: str, repo: str, n: int = 20) -> list[dict[str, Any]]:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    v.id,
                    v.vote,
                    v.critique_text,
                    v.severity,
                    v.confidence,
                    v.timestamp,
                    c.correction AS correction,
                    c.note AS correction_note
                FROM verdicts v
                LEFT JOIN corrections c
                  ON c.id = (
                    SELECT c2.id
                    FROM corrections c2
                    WHERE c2.verdict_id = v.id
                    ORDER BY c2.id DESC
                    LIMIT 1
                  )
                WHERE agent_name = ? AND repo = ?
                ORDER BY v.id DESC
                LIMIT ?
                """,
                (agent_name, repo or "unknown", int(n)),
            ).fetchall()
    return [dict(r) for r in rows]


def save_correction(verdict_id: int, corrected_by: str, correction: str, note: str) -> None:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO corrections (verdict_id, corrected_by, correction, note)
                VALUES (?, ?, ?, ?)
                """,
                (int(verdict_id), corrected_by, correction, note),
            )
            conn.commit()


def get_latest_verdict_id(pr_number: int, repo: str) -> int | None:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM verdicts
                WHERE pr_number = ? AND repo = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(pr_number), repo or "unknown"),
            ).fetchone()
    if not row:
        return None
    return int(row["id"])


def record_coverage_signal(pr_number: int, repo: str, coverage_score: float, quality_label: str) -> None:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO coverage_signals (pr_number, repo, coverage_score, quality_label)
                VALUES (?, ?, ?, ?)
                """,
                (pr_number, repo or "unknown", float(coverage_score), quality_label),
            )
            conn.commit()


def get_false_positive_rate(agent_name: str, repo: str) -> float:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN c.correction = 'false_positive' THEN 1 ELSE 0 END) AS fp,
                    COUNT(c.id) AS total
                FROM verdicts v
                LEFT JOIN corrections c ON c.verdict_id = v.id
                WHERE v.agent_name = ? AND v.repo = ?
                """,
                (agent_name, repo or "unknown"),
            ).fetchone()
    fp = int(row["fp"] or 0) if row else 0
    total = int(row["total"] or 0) if row else 0
    if total == 0:
        return 0.0
    return fp / total


def get_recent_coverage_scores(repo: str, limit: int = 5) -> list[float]:
    init_feedback_store()
    with _LOCK:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT coverage_score
                FROM coverage_signals
                WHERE repo = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (repo or "unknown", int(limit)),
            ).fetchall()
    return [float(r["coverage_score"]) for r in rows]
