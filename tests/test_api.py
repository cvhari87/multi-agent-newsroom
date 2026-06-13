"""Tests for the FastAPI endpoints — no real pipeline or Anthropic calls."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from newsroom import db


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point every test at a throwaway SQLite file."""
    db_path = tmp_path / "newsroom.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from newsroom.api import app

    return TestClient(app)


def _seed_run(run_id: str = "run-1", status: str = "complete") -> None:
    db.create_run(run_id)
    if status == "complete":
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        with db._connect() as conn:
            conn.execute(
                "UPDATE runs SET status='complete', finished_at=?, story_count=1, "
                "eval_score_avg=8.0, briefing_path='output/briefing.md' WHERE id=?",
                (now, run_id),
            )


def _seed_story(run_id: str = "run-1", story_id: str = "story-1") -> None:
    with db._connect() as conn:
        conn.execute(
            """INSERT INTO stories (
                id, run_id, title, url, summary, angle, full_briefing,
                topic_tags, sources_json, confidence_score, cross_source_count,
                eval_score, eval_notes, published_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                story_id,
                run_id,
                "Test Story",
                "https://example.com/story",
                "A test summary",
                "Why this matters",
                "# Full briefing markdown",
                json.dumps(["LLMs", "Tooling"]),
                json.dumps([{"name": "Source", "url": "https://example.com"}]),
                0.9,
                2,
                8.5,
                "",
                "2026-06-12T00:00:00Z",
                "2026-06-12T12:00:00Z",
            ),
        )


# ------------------------------------------------------------------
# GET /api/runs
# ------------------------------------------------------------------
def test_get_runs_empty(client) -> None:
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_get_runs_returns_seeded_run(client) -> None:
    _seed_run("run-1")
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["status"] == "complete"


# ------------------------------------------------------------------
# GET /api/stories
# ------------------------------------------------------------------
def test_get_stories_empty(client) -> None:
    resp = client.get("/api/stories")
    assert resp.status_code == 200
    assert resp.json() == {"stories": []}


def test_get_stories_returns_seeded_story(client) -> None:
    _seed_run("run-1")
    _seed_story("run-1", "story-1")
    resp = client.get("/api/stories")
    assert resp.status_code == 200
    stories = resp.json()["stories"]
    assert len(stories) == 1
    assert stories[0]["title"] == "Test Story"
    assert stories[0]["topic_tags"] == ["LLMs", "Tooling"]


def test_get_stories_filters_by_tag(client) -> None:
    _seed_run("run-1")
    _seed_story("run-1", "story-1")
    resp = client.get("/api/stories?tag=LLMs")
    assert len(resp.json()["stories"]) == 1

    resp = client.get("/api/stories?tag=Safety")
    assert len(resp.json()["stories"]) == 0


# ------------------------------------------------------------------
# GET /api/stories/{id}
# ------------------------------------------------------------------
def test_get_story_detail(client) -> None:
    _seed_run("run-1")
    _seed_story("run-1", "story-1")
    resp = client.get("/api/stories/story-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Story"
    assert data["full_briefing"] == "# Full briefing markdown"
    assert data["sources"] == [{"name": "Source", "url": "https://example.com"}]


def test_get_story_not_found(client) -> None:
    resp = client.get("/api/stories/nonexistent")
    assert resp.status_code == 404
