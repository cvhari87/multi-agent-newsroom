import json
import sqlite3

from newsroom import db


def test_failed_run_is_persisted_with_audit_event(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "newsroom.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)

    db.create_run("run-1")
    db.fail_run("run-1", "boom")

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM runs WHERE id='run-1'").fetchone()[0]
        details = conn.execute(
            "SELECT details FROM run_events WHERE run_id='run-1' AND event='failed'"
        ).fetchone()[0]

    assert status == "failed"
    assert json.loads(details) == {"error": "boom"}


def test_artifact_is_persisted(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "newsroom.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.create_run("run-1")

    artifact_id = db.save_artifact("run-1", "research", [{"url": "https://example.com"}])

    with sqlite3.connect(db_path) as conn:
        payload = conn.execute(
            "SELECT payload FROM artifacts WHERE id=?",
            (artifact_id,),
        ).fetchone()[0]

    assert json.loads(payload) == [{"url": "https://example.com"}]
