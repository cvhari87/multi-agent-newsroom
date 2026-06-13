import sqlite3

import pytest

from newsroom import db, orchestrator


def test_pipeline_marks_run_failed_when_child_raises(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "newsroom.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        orchestrator.research,
        "run",
        lambda: (_ for _ in ()).throw(RuntimeError("research unavailable")),
    )

    with pytest.raises(RuntimeError, match="research unavailable"):
        orchestrator.run_pipeline()

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM runs").fetchone()[0]

    assert status == "failed"
