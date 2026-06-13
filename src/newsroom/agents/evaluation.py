"""Evaluation agent — scores briefings and returns structured packets to the parent."""

import json
import os

import anthropic

from newsroom.citations import citation_issues
from newsroom.models import MODEL, EvaluatedStory, EvaluationPacket, WrittenStory
from newsroom.structured import index_complete_results, parse_json_array, require_fields

SYSTEM_PROMPT = """\
You are the Evaluation agent for an AI engineering newsletter.

Independently assess each briefing for:
1. eval_score (0–10):
   - 9–10: excellent — clear, well-cited, insightful, no duplication
   - 7–8:  good — minor issues only
   - 5–6:  acceptable — citation gaps or weak angle
   - <5:   flag — missing citations, duplicate content, or factual concerns
2. recommendation: "approve" | "revise" | "reject"
   - approve: score >= 7 and no fundamental issues
   - revise:  score >= 5 with specific fixable issues
   - reject:  score < 5 or unfixable structural problem
3. issues: list of specific problems found (empty list if none)

Judge factual support only against source_evidence and supporting_sources supplied
for that story. Treat citations outside supporting_sources as unsupported.

Return a JSON array with exactly one object per input briefing:
[
  {
    "url": "https://...",
    "eval_score": 8.5,
    "recommendation": "approve",
    "issues": []
  },
  {
    "eval_score": 5.0,
    "recommendation": "revise",
    "issues": ["Missing citation for the benchmark claim in paragraph 2.", "Angle not addressed in conclusion."]
  },
  ...
]

Return ONLY the JSON array."""


def run(stories: list[WrittenStory]) -> list[EvaluationPacket]:
    if not stories:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    payload = json.dumps(
        [
            {
                "title": s["title"],
                "url": s["url"],
                "angle": s["angle"],
                "full_briefing": s["full_briefing"],
                "sources_json": s["sources_json"],
                "supporting_sources": s["supporting_sources"],
                "source_evidence": [
                    {
                        **source,
                        "evidence_text": source["evidence_text"][:3000],
                    }
                    for source in s["evidence_sources"]
                ],
            }
            for s in stories
        ],
        indent=2,
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
    )

    results = index_complete_results(
        parse_json_array(msg.content[0].text),
        (story["url"] for story in stories),
    )

    packets: list[EvaluationPacket] = []
    for story in stories:
        r = results[story["url"]]
        require_fields(
            r,
            ("eval_score", "recommendation", "issues"),
            url=story["url"],
        )
        deterministic_issues = citation_issues(story)
        model_issues = r.get("issues", [])
        issues = [*deterministic_issues, *model_issues]
        score = round(float(r.get("eval_score", 5.0)), 1)
        recommendation = r.get("recommendation", "reject")
        if deterministic_issues:
            score = min(score, 4.0)
            recommendation = "reject"

        packets.append(
            EvaluationPacket(
                story=EvaluatedStory(
                    **story,
                    eval_score=score,
                    eval_notes="; ".join(issues),
                ),
                recommendation=recommendation,
                issues=issues,
            )
        )

    return packets
