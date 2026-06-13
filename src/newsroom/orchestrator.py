"""Orchestrator — the Newsroom Editor (parent) drives the child agents."""

import time
import uuid
from collections import defaultdict

from newsroom import db
from newsroom.agents import editorial, evaluation, output, research, verification, writing
from newsroom.editor import MAX_REVISIONS, NewsroomEditor
from newsroom.models import EvaluatedStory, WrittenStory


class RunCancelledError(Exception):
    """Raised when a run is cancelled mid-pipeline."""


def _check_cancelled(run_id: str) -> None:
    """Raise if the run has been cancelled."""
    if db.is_cancelled(run_id):
        raise RunCancelledError(f"Run {run_id} was cancelled")


def run_pipeline() -> str:
    run_id = str(uuid.uuid4())
    db.create_run(run_id)

    try:
        return _run_pipeline(run_id)
    except RunCancelledError:
        # Already marked cancelled in DB — don't overwrite with 'failed'
        raise
    except Exception as exc:
        db.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _run_pipeline(run_id: str) -> str:
    editor = NewsroomEditor()
    pipeline_start = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Research — fetch RSS + summarize articles in parallel
    # ------------------------------------------------------------------
    db.update_stage(run_id, "research")
    t = time.monotonic()
    print(f"[{_ts()}] 1/6  Research    — fetching and summarizing articles…")
    raw = research.run()
    artifact_id = db.save_artifact(run_id, "research", raw)
    db.record_event(run_id, "research", "completed", {"story_count": len(raw), "artifact_id": artifact_id})
    print(f"[{_ts()}]      {len(raw)} articles collected ({time.monotonic()-t:.1f}s)")
    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 2. Verification — child scores each story
    # ------------------------------------------------------------------
    db.update_stage(run_id, "verification")
    t = time.monotonic()
    print(f"[{_ts()}] 2/6  Verification — scoring confidence and cross-source coverage…")
    ver_packets = verification.run(raw)
    artifact_id = db.save_artifact(run_id, "verification", ver_packets)
    db.record_event(run_id, "verification", "completed", {"packet_count": len(ver_packets), "artifact_id": artifact_id})
    print(f"[{_ts()}]      verification done ({time.monotonic()-t:.1f}s)")
    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 3. Editor reviews verification results
    # ------------------------------------------------------------------
    db.update_stage(run_id, "editor_review")
    t = time.monotonic()
    print(f"[{_ts()}]      Editor reviewing verification results…")
    ver_decisions = editor.review_verification(ver_packets)
    db.record_event(run_id, "parent", "verification_reviewed", {"decisions": ver_decisions})

    decision_map = {d["url"]: d for d in ver_decisions}
    MAX_TO_EDITORIAL = 20
    accepted = [
        p["story"]
        for p in ver_packets
        if decision_map.get(p["story"]["url"], {}).get("action") == "accept"
    ]
    accepted.sort(key=lambda s: s["confidence_score"], reverse=True)
    accepted = accepted[:MAX_TO_EDITORIAL]
    print(f"[{_ts()}]      {len(accepted)} accepted, {len(raw) - len(accepted)} rejected/pruned ({time.monotonic()-t:.1f}s)")

    if not accepted:
        print(f"[{_ts()}]      No stories passed verification. Exiting.")
        return output.run([], run_id)

    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 4. Editorial — child ranks and selects angles
    # ------------------------------------------------------------------
    db.update_stage(run_id, "editorial")
    t = time.monotonic()
    print(f"[{_ts()}] 3/6  Editorial   — ranking stories and selecting angles…")
    ed_packets = editorial.run(accepted)
    artifact_id = db.save_artifact(run_id, "editorial", ed_packets)
    db.record_event(run_id, "editorial", "completed", {"packet_count": len(ed_packets), "artifact_id": artifact_id})
    selected = [p["story"] for p in ed_packets]
    print(f"[{_ts()}]      {len(selected)} stories selected ({time.monotonic()-t:.1f}s)")

    if not selected:
        print(f"[{_ts()}]      No stories selected. Exiting.")
        return output.run([], run_id)

    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 5. Writing — child drafts briefings in parallel
    # ------------------------------------------------------------------
    db.update_stage(run_id, "writing")
    t = time.monotonic()
    print(f"[{_ts()}] 4/6  Writing     — drafting briefings in parallel…")
    wr_packets = writing.run(selected)
    artifact_id = db.save_artifact(run_id, "writing", wr_packets)
    db.record_event(run_id, "writing", "completed", {"packet_count": len(wr_packets), "artifact_id": artifact_id})
    print(f"[{_ts()}]      {len(wr_packets)} briefings drafted ({time.monotonic()-t:.1f}s)")
    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 6. Evaluation — child scores each briefing
    # ------------------------------------------------------------------
    db.update_stage(run_id, "evaluation")
    t = time.monotonic()
    print(f"[{_ts()}] 5/6  Evaluation  — scoring quality…")
    ev_packets = evaluation.run([p["story"] for p in wr_packets])
    artifact_id = db.save_artifact(run_id, "evaluation", ev_packets)
    db.record_event(run_id, "evaluation", "completed", {"packet_count": len(ev_packets), "artifact_id": artifact_id})
    avg = (
        sum(ep["story"]["eval_score"] for ep in ev_packets) / len(ev_packets)
        if ev_packets
        else 0.0
    )
    print(f"[{_ts()}]      avg eval score {avg:.1f}/10 ({time.monotonic()-t:.1f}s)")

    # ------------------------------------------------------------------
    # 7. Revision loop — editor approves, routes revisions, or rejects
    # ------------------------------------------------------------------
    revision_counts: dict[str, int] = defaultdict(int)
    final_stories: list[EvaluatedStory] = []
    pending_wr = wr_packets
    pending_ev = ev_packets

    while True:
        _check_cancelled(run_id)
        db.update_stage(run_id, "revision_loop")
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

    _check_cancelled(run_id)

    # ------------------------------------------------------------------
    # 8. Output — deterministic service writes briefing + persists to DB
    # ------------------------------------------------------------------
    db.update_stage(run_id, "output")
    print(f"[{_ts()}] 6/6  Output      — writing briefing file and persisting to SQLite…")
    path = output.run(final_stories, run_id)
    print(f"[{_ts()}]      Pipeline complete in {time.monotonic() - pipeline_start:.1f}s -> {path}")

    return path
