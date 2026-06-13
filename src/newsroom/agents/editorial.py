"""Editorial agent — ranks verified stories, selects angles, returns packets to parent."""

import json
import os

import anthropic

from newsroom.models import MODEL, EditorialPacket, EditorialStory, VerifiedStory

MAX_STORIES = 8

SYSTEM_PROMPT = """\
You are the Editorial agent for a daily AI engineering newsletter.

Given a list of verified stories, select the most newsworthy (max 8) and for each:
1. Assign 1–3 topic_tags from: LLMs, Tooling, Infrastructure, Research, Safety, Agents, Data, Benchmarks, Open Source, Industry
2. Write a one-sentence angle — the specific lens this newsletter should take
3. Assign a rank (1 = most important)
4. Write a one-sentence rationale explaining why this story was selected

Return a JSON array of SELECTED stories in ranked order:
[
  {
    "url": "<original url>",
    "topic_tags": ["LLMs", "Research"],
    "angle": "Why this matters for engineers building production LLM systems.",
    "rank": 1,
    "rationale": "First benchmark showing regression in tool-use across major models."
  },
  ...
]

Return ONLY the JSON array."""


def _parse(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def run(stories: list[VerifiedStory]) -> list[EditorialPacket]:
    if not stories:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    payload = json.dumps(
        [
            {
                "url": s["url"],
                "title": s["title"],
                "summary": s["summary"],
                "source": s["source_name"],
                "confidence_score": s["confidence_score"],
                "cross_source_count": s["cross_source_count"],
                "supporting_sources": s["supporting_sources"],
                "evidence_status": s["evidence_status"],
                "verification_caveats": s["verification_caveats"],
            }
            for s in stories
        ],
        indent=2,
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
    )

    selections = _parse(msg.content[0].text)
    by_url = {s["url"]: s for s in stories}

    packets: list[EditorialPacket] = []
    for sel in selections[:MAX_STORIES]:
        source = by_url.get(sel.get("url", ""))
        if not source:
            continue
        packets.append(
            EditorialPacket(
                story=EditorialStory(
                    **source,
                    angle=sel.get("angle", ""),
                    topic_tags=sel.get("topic_tags", []),
                    rank=int(sel.get("rank", len(packets) + 1)),
                ),
                rationale=sel.get("rationale", ""),
            )
        )

    packets.sort(key=lambda p: p["story"]["rank"])
    return packets
