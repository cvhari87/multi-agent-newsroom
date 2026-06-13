"""Newsroom Editor — the parent agent that reviews child packets and makes decisions."""

import json
import os

import anthropic

from newsroom.models import (
    MODEL,
    EvaluationPacket,
    ParentDecision,
    VerificationPacket,
)
from newsroom.structured import index_complete_results, parse_json_array, require_fields

MAX_REVISIONS = 2
PASS_SCORE = 7.0

SYSTEM_PROMPT = """\
You are the Newsroom Editor — the senior decision-maker for an AI engineering newsletter.

You receive compact result packets from specialist child agents and make editorial decisions.
You are the only agent allowed to accept, approve, revise, or reject content.

Rules:
- Base decisions on the child agent's recommendation and evidence, but use your own judgement.
- For revisions, provide specific, actionable feedback the Writing agent can act on.
- Be decisive. A story either moves forward or it doesn't.

Respond with compact JSON only."""

VERIFY_DECISION_PROMPT = """\
Review these verification results and decide: accept or reject each story.

Guidelines:
- accept: confidence >= 0.5 and relevant to AI engineering practitioners
- accept "research_more" if confidence >= 0.4 and the topic is important enough
- reject: off-topic, confidence < 0.4, or too speculative to be useful

Return a JSON array, SAME ORDER as input:
[{"url": "...", "action": "accept"|"reject", "reason": "<one sentence>", "feedback": ""}, ...]

Return ONLY the JSON array."""

EVAL_DECISION_PROMPT_TEMPLATE = """\
Review these evaluation results and decide: approve, revise, or reject each story.
Max revisions allowed per story: {max_revisions}. Current revision counts are included.

Guidelines:
- approve: eval_score >= {pass_score} (or no fixable issues remain)
- revise: eval_score >= 5.0, revision budget available, and issues are addressable
- reject: eval_score < 5.0, or revision budget exhausted, or issues are fundamental

For "revise" actions, provide specific feedback the Writing agent must address.

Return a JSON array, SAME ORDER as input:
[{{"url": "...", "action": "approve"|"revise"|"reject", "reason": "<one sentence>", "feedback": "<revision instructions or empty>"}}, ...]

Return ONLY the JSON array."""


class NewsroomEditor:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def _decide(
        self,
        task_prompt: str,
        payload: str,
        expected_urls: list[str],
    ) -> list[ParentDecision]:
        msg = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"{task_prompt}\n\nData:\n{payload}"},
            ],
        )
        raw = index_complete_results(parse_json_array(msg.content[0].text), expected_urls)
        decisions: list[ParentDecision] = []
        for url in expected_urls:
            result = raw[url]
            require_fields(result, ("action",), url=url)
            decisions.append(
                ParentDecision(
                    url=url,
                    action=result["action"],
                    reason=result.get("reason", ""),
                    feedback=result.get("feedback", ""),
                )
            )
        return decisions

    def review_verification(
        self, packets: list[VerificationPacket]
    ) -> list[ParentDecision]:
        """Accept or reject stories after Verification."""
        payload = json.dumps(
            [
                {
                    "url": p["story"]["url"],
                    "title": p["story"]["title"],
                    "confidence_score": p["story"]["confidence_score"],
                    "cross_source_count": p["story"]["cross_source_count"],
                    "recommendation": p["recommendation"],
                    "caveats": p["caveats"],
                }
                for p in packets
            ],
            indent=2,
        )
        return self._decide(
            VERIFY_DECISION_PROMPT,
            payload,
            [p["story"]["url"] for p in packets],
        )

    def review_evaluation(
        self,
        packets: list[EvaluationPacket],
        revision_counts: dict[str, int],
    ) -> list[ParentDecision]:
        """Approve, revise, or reject stories after Evaluation."""
        task_prompt = EVAL_DECISION_PROMPT_TEMPLATE.format(
            max_revisions=MAX_REVISIONS,
            pass_score=PASS_SCORE,
        )
        payload = json.dumps(
            [
                {
                    "url": p["story"]["url"],
                    "title": p["story"]["title"],
                    "eval_score": p["story"]["eval_score"],
                    "recommendation": p["recommendation"],
                    "issues": p["issues"],
                    "revisions_used": revision_counts.get(p["story"]["url"], 0),
                    "revisions_remaining": MAX_REVISIONS
                    - revision_counts.get(p["story"]["url"], 0),
                }
                for p in packets
            ],
            indent=2,
        )
        return self._decide(
            task_prompt,
            payload,
            [p["story"]["url"] for p in packets],
        )
