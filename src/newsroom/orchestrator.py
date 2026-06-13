"""Orchestrator — the Newsroom Editor (parent) drives the child agents."""

import uuid
from collections import defaultdict

from newsroom import db
from newsroom.agents import editorial, evaluation, output, research, verification, writing
from newsroom.editor import MAX_REVISIONS, NewsroomEditor
from newsroom.models import EvaluatedStory, WrittenStory


def run_pipeline() -> str:
    run_id = str(uuid.uuid4())
    db.create_run(run_id)

    try:
        return _run_pipeline(run_id)
    except Exception as exc:
        db.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise


def _run_pipeline(run_id: str) -> str:
    editor = NewsroomEditor()
    # ------------------------------------------------------------------
    # 1. Research — fetch RSS + summarize articles in parallel
    # ------------------------------------------------------------------
    print("1/6  Research    — fetching and summarizing articles…")
    raw = research.run()
    artifact_id = db.save_artifact(run_id, "research", raw)
    db.record_event(
        run_id,
        "research",
        "completed",
        {"story_count": len(raw), "artifact_id": artifact_id},
    )
    print(f"     {len(raw)} articles collected")

    # ------------------------------------------------------------------
    # 2. Verification — child scores each story
    # ------------------------------------------------------------------
    print("2/6  Verification — scoring confidence and cross-source coverage…")
    ver_packets = verification.run(raw)
    artifact_id = db.save_artifact(run_id, "verification", ver_packets)
    db.record_event(
        run_id,
        "verification",
        "completed",
        {"packet_count": len(ver_packets), "artifact_id": artifact_id},
    )

    # ------------------------------------------------------------------
    # 3. Editor reviews verification results
    # ------------------------------------------------------------------
    print("     Editor reviewing verification results…")
    ver_decisions = editor.review_verification(ver_packets)
    db.record_event(
        run_id,
        "parent",
        "verification_reviewed",
        {"decisions": ver_decisions},
    )

    decision_map = {d["url"]: d for d in ver_decisions}
    MAX_TO_EDITORIAL = 20
    accepted = [
        p["story"]
        for p in ver_packets
        if decision_map.get(p["story"]["url"], {}).get("action") == "accept"
    ]
    accepted.sort(key=lambda s: s["confidence_score"], reverse=True)
    accepted = accepted[:MAX_TO_EDITORIAL]
    print(f"     {len(accepted)} accepted (capped at {MAX_TO_EDITORIAL}), {len(raw) - len(accepted)} rejected/pruned")

    if not accepted:
        print("     No stories passed verification. Exiting.")
        return output.run([], run_id)

    # ------------------------------------------------------------------
    # 4. Editorial — child ranks and selects angles
    # ------------------------------------------------------------------
    print("3/6  Editorial   — ranking stories and selecting angles…")
    ed_packets = editorial.run(accepted)
    artifact_id = db.save_artifact(run_id, "editorial", ed_packets)
    db.record_event(
        run_id,
        "editorial",
        "completed",
        {"packet_count": len(ed_packets), "artifact_id": artifact_id},
    )
    selected = [p["story"] for p in ed_packets]
    print(f"     {len(selected)} stories selected for briefing")

    if not selected:
        print("     No stories selected. Exiting.")
        return output.run([], run_id)

    # ------------------------------------------------------------------
    # 5. Writing — child drafts briefings in parallel
    # ------------------------------------------------------------------
    print("4/6  Writing     — drafting briefings in parallel…")
    wr_packets = writing.run(selected)
    artifact_id = db.save_artifact(run_id, "writing", wr_packets)
    db.record_event(
        run_id,
        "writing",
        "completed",
        {"packet_count": len(wr_packets), "artifact_id": artifact_id},
    )
    print(f"     {len(wr_packets)} briefings drafted")

    # ------------------------------------------------------------------
    # 6. Evaluation — child scores each briefing
    # ------------------------------------------------------------------
    print("5/6  Evaluation  — scoring quality…")
    ev_packets = evaluation.run([p["story"] for p in wr_packets])
    artifact_id = db.save_artifact(run_id, "evaluation", ev_packets)
    db.record_event(
        run_id,
        "evaluation",
        "completed",
        {"packet_count": len(ev_packets), "artifact_id": artifact_id},
    )
    avg = (
        sum(ep["story"]["eval_score"] for ep in ev_packets) / len(ev_packets)
        if ev_packets
        else 0.0
    )
    print(f"     avg eval score: {avg:.1f}/10")

    # ------------------------------------------------------------------
    # 7. Revision loop — editor approves, routes revisions, or rejects
    # ------------------------------------------------------------------
    revision_counts: dict[str, int] = defaultdict(int)
    final_stories: list[EvaluatedStory] = []
    pending_wr = wr_packets
    pending_ev = ev_packets

    while True:
        print("     Editor reviewing evaluation results…")
        decisions = editor.review_evaluation(pending_ev, dict(revision_counts))
        db.record_event(
            run_id,
            "parent",
            "evaluation_reviewed",
            {"decisions": decisions, "revision_counts": dict(revision_counts)},
        )
        dec_map = {d["url"]: d for d in decisions}
        writing_by_url = {packet["story"]["url"]: packet for packet in pending_wr}

        next_round: list[tuple[WrittenStory, str]] = []  # (story, feedback)
        for ep in pending_ev:
            url = ep["story"]["url"]
            wp = writing_by_url.get(url)
            if wp is None:
                raise ValueError(f"Missing writing packet for evaluated story: {url}")
            d = dec_map.get(url, {"action": "reject", "feedback": ""})

            if d["action"] == "approve":
                final_stories.append(ep["story"])
            elif d["action"] == "revise" and revision_counts[url] < MAX_REVISIONS:
                revision_counts[url] += 1
                feedback_text = (
                    f"Previous draft:\n{wp['story']['full_briefing']}\n\n"
                    f"Issues to fix:\n{d['feedback']}"
                )
                next_round.append((wp["story"], feedback_text))
                print(
                    f"     Revision {revision_counts[url]}/{MAX_REVISIONS}: "
                    f"{ep['story']['title'][:60]}…"
                )
            # else: reject — silently drop

        if not next_round:
            break

        feedback_map = {s["url"]: fb for s, fb in next_round}
        stories_to_revise = [s for s, _ in next_round]
        rev_num = max(revision_counts[s["url"]] for s in stories_to_revise)

        pending_wr = writing.run(stories_to_revise, feedback=feedback_map, revision_number=rev_num)
        pending_ev = evaluation.run([p["story"] for p in pending_wr])
        writing_artifact_id = db.save_artifact(run_id, f"writing_revision_{rev_num}", pending_wr)
        evaluation_artifact_id = db.save_artifact(
            run_id,
            f"evaluation_revision_{rev_num}",
            pending_ev,
        )
        db.record_event(
            run_id,
            "revision",
            "completed",
            {
                "story_count": len(pending_ev),
                "revision_number": rev_num,
                "writing_artifact_id": writing_artifact_id,
                "evaluation_artifact_id": evaluation_artifact_id,
            },
        )

    approved = len(final_stories)
    total = len(selected)
    print(f"     {approved}/{total} stories approved, {total - approved} rejected")

    # ------------------------------------------------------------------
    # 8. Output — deterministic service writes briefing + persists to DB
    # ------------------------------------------------------------------
    print("6/6  Output      — writing briefing file and persisting to SQLite…")
    path = output.run(final_stories, run_id)

    return path
