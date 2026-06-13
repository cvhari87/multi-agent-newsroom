"""Output agent — writes briefing.md and persists stories to SQLite."""

import uuid
from datetime import date
from pathlib import Path

from newsroom import db
from newsroom.models import EvaluatedStory

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"


def run(stories: list[EvaluatedStory], run_id: str) -> str:
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    path = OUTPUT_DIR / f"briefing-{today}.md"

    lines: list[str] = [
        f"# AI Engineering Briefing — {today}",
        "",
        f"*{len(stories)} stories · run `{run_id[:8]}`*",
        "",
        "---",
        "",
    ]

    for story in stories:
        score_str = f"{story['eval_score']:.1f}/10"
        flag = " ⚠️" if story["eval_score"] < 5 else ""
        tags = " · ".join(f"`{t}`" for t in story["topic_tags"])

        lines += [
            f"## {story['title']}",
            "",
            f"**Source:** [{story['source_name']}]({story['url']})  ",
            f"**Tags:** {tags}  ",
            f"**Eval:** {score_str}{flag}",
            "",
            f"*Angle: {story['angle']}*",
            "",
            story["full_briefing"],
            "",
        ]

        if story["eval_notes"]:
            lines += [f"> **QC Note:** {story['eval_notes']}", ""]

        lines += ["---", ""]

    path.write_text("\n".join(lines), encoding="utf-8")

    # persist to SQLite
    for story in stories:
        db.insert_story(story, run_id, str(uuid.uuid4()))

    db.complete_run(run_id, stories, str(path))

    return str(path)
