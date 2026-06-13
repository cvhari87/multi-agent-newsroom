from unittest.mock import patch

from newsroom.cli import main


def test_main_prints_ready_message(capsys) -> None:
    with patch("newsroom.orchestrator.run_pipeline", return_value="/tmp/briefing-test.md"):
        main()

    out = capsys.readouterr().out
    assert "Multi-Agent Newsroom is ready." in out
    assert "briefing" in out
