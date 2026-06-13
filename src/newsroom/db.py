"""SQLite persistence — runs and stories tables."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from newsroom.models import EvaluatedStory

DB_PATH = Path(__file__).resolve().parents[2] / "newsroom.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id            TEXT PRIMARY KEY,
                status        TEXT NOT NULL DEFAULT 'running',
                started_at    TEXT NOT NULL,
                finished_at   TEXT,
                story_count   INTEGER,
                eval_score_avg REAL,
                briefing_path TEXT
            );

            CREATE TABLE IF NOT EXISTS stories (
                id                  TEXT PRIMARY KEY,
                run_id              TEXT NOT NULL REFERENCES runs(id),
                title               TEXT,
                url                 TEXT,
                summary             TEXT,
                angle               TEXT,
                full_briefing       TEXT,
                topic_tags          TEXT,
                sources_json        TEXT,
                confidence_score    REAL,
                cross_source_count  INTEGER,
                eval_score          REAL,
                eval_notes          TEXT,
                published_at        TEXT,
                created_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS run_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL REFERENCES runs(id),
                stage       TEXT NOT NULL,
                event       TEXT NOT NULL,
                details     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id          TEXT PRIMARY KEY,
                run_id      TEXT NOT NULL REFERENCES runs(id),
                stage       TEXT NOT NULL,
                payload     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)


def create_run(run_id: str) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, status, started_at) VALUES (?, 'running', ?)",
            (run_id, now),
        )
    record_event(run_id, "run", "started", {})


def record_event(run_id: str, stage: str, event: str, details: dict) -> None:
    """Persist a compact audit event for parent-child workflow decisions."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO run_events (run_id, stage, event, details, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, stage, event, json.dumps(details), now),
        )


def save_artifact(run_id: str, stage: str, payload: object) -> str:
    """Persist a complete stage artifact and return its ID."""
    artifact_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO artifacts (id, run_id, stage, payload, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (artifact_id, run_id, stage, json.dumps(payload), now),
        )
    return artifact_id


def fail_run(run_id: str, error: str) -> None:
    """Mark a run failed and retain the failure reason."""
    now = datetime.now(timezone.utc).isoformat()
    record_event(run_id, "run", "failed", {"error": error})
    with _connect() as conn:
        conn.execute(
            "UPDATE runs SET status='failed', finished_at=? WHERE id=?",
            (now, run_id),
        )


def insert_story(story: EvaluatedStory, run_id: str, story_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO stories (
                id, run_id, title, url, summary, angle, full_briefing,
                topic_tags, sources_json, confidence_score, cross_source_count,
                eval_score, eval_notes, published_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                story_id,
                run_id,
                story["title"],
                story["url"],
                story["summary"],
                story["angle"],
                story["full_briefing"],
                json.dumps(story["topic_tags"]),
                json.dumps(story["sources_json"]),
                story["confidence_score"],
                story["cross_source_count"],
                story["eval_score"],
                story["eval_notes"],
                story["published_at"],
                now,
            ),
        )


def complete_run(run_id: str, stories: list[EvaluatedStory], briefing_path: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    avg = sum(s["eval_score"] for s in stories) / len(stories) if stories else 0.0
    with _connect() as conn:
        conn.execute(
            """UPDATE runs SET status='complete', finished_at=?, story_count=?,
               eval_score_avg=?, briefing_path=? WHERE id=?""",
            (now, len(stories), round(avg, 2), briefing_path, run_id),
        )
    record_event(
        run_id,
        "run",
        "completed",
        {"story_count": len(stories), "briefing_path": briefing_path},
    )


# ---------------------------------------------------------------------------
# Read helpers — used by the API layer
# ---------------------------------------------------------------------------

def list_runs() -> list[dict]:
    """Return all runs, newest first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, status, started_at, finished_at, story_count, eval_score_avg, briefing_path "
            "FROM runs ORDER BY started_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_stories(*, run_id: str | None = None, tag: str | None = None) -> list[dict]:
    """Return story cards. Defaults to the most recent completed run."""
    init_db()
    with _connect() as conn:
        if run_id is None:
            row = conn.execute(
                "SELECT id FROM runs WHERE status='complete' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return []
            run_id = row["id"]

        rows = conn.execute(
            "SELECT id, run_id, title, url, summary, angle, topic_tags, "
            "eval_score, cross_source_count, confidence_score, published_at "
            "FROM stories WHERE run_id=? ORDER BY eval_score DESC",
            (run_id,),
        ).fetchall()

    stories = []
    for r in rows:
        d = dict(r)
        d["topic_tags"] = json.loads(d["topic_tags"]) if d["topic_tags"] else []
        d["source_count"] = d.pop("cross_source_count", 0)
        if tag and tag not in d["topic_tags"]:
            continue
        stories.append(d)
    return stories


def get_story(story_id: str) -> dict | None:
    """Return full story detail including briefing and citations."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, run_id, title, url, summary, angle, full_briefing, topic_tags, "
            "sources_json, confidence_score, cross_source_count, eval_score, eval_notes, "
            "published_at, created_at "
            "FROM stories WHERE id=?",
            (story_id,),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["topic_tags"] = json.loads(d["topic_tags"]) if d["topic_tags"] else []
    d["sources"] = json.loads(d["sources_json"]) if d["sources_json"] else []
    del d["sources_json"]
    return d
