"""Verification agent — scores stories and returns structured packets to the parent."""

import json
import os

import anthropic

from newsroom.models import MODEL, RawStory, VerificationPacket, VerifiedStory
from newsroom.structured import index_complete_results, parse_json_array, require_fields

SYSTEM_PROMPT = """\
You are the Verification agent for an AI engineering newsletter.

For each story, assess only what the supplied evidence supports:
1. confidence_score (0.0–1.0): credibility based on the supplied source evidence
2. supporting_urls: URLs from the supplied candidate set that independently cover the same event
3. recommendation: "accept" | "research_more" | "reject"
   - accept: credible, relevant to AI engineering, sufficient evidence
   - research_more: plausible but needs more sources or has gaps
   - reject: off-topic, too speculative, or low credibility
4. caveats: list of specific concerns (empty list if none)

Never estimate or invent source coverage. If no other supplied candidate covers the
same event, supporting_urls must contain only the story's own URL.

Return a JSON array with exactly one object per input story:
[
  {
    "url": "https://...",
    "confidence_score": 0.85,
    "supporting_urls": ["https://..."],
    "recommendation": "accept",
    "caveats": []
  },
  ...
]

Return ONLY the JSON array."""


def run(stories: list[RawStory]) -> list[VerificationPacket]:
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
                "evidence_status": s["evidence_status"],
                "evidence_text": s["evidence_text"][:1500],
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

    results = index_complete_results(
        parse_json_array(msg.content[0].text),
        (story["url"] for story in stories),
    )
    by_url = {story["url"]: story for story in stories}

    packets: list[VerificationPacket] = []
    for story in stories:
        r = results[story["url"]]
        require_fields(
            r,
            ("confidence_score", "supporting_urls", "recommendation", "caveats"),
            url=story["url"],
        )
        supporting_urls = r.get("supporting_urls", [story["url"]])
        if not isinstance(supporting_urls, list):
            supporting_urls = [story["url"]]
        valid_supporting_urls = list(
            dict.fromkeys(
                url for url in supporting_urls if isinstance(url, str) and url in by_url
            )
        )
        if story["url"] not in valid_supporting_urls:
            valid_supporting_urls.insert(0, story["url"])
        supporting_sources = [
            {"name": by_url[url]["source_name"], "url": url}
            for url in valid_supporting_urls
        ]
        evidence_sources = [
            {
                "name": by_url[url]["source_name"],
                "url": url,
                "evidence_text": by_url[url]["evidence_text"],
            }
            for url in valid_supporting_urls
        ]
        packets.append(
            VerificationPacket(
                story=VerifiedStory(
                    **story,
                    confidence_score=round(float(r.get("confidence_score", 0.5)), 3),
                    cross_source_count=len(supporting_sources),
                    supporting_sources=supporting_sources,
                    evidence_sources=evidence_sources,
                    verification_caveats=r["caveats"],
                ),
                recommendation=r.get("recommendation", "accept"),
                caveats=r.get("caveats", []),
            )
        )

    return packets
