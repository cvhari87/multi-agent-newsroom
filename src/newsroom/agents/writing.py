"""Writing agent — drafts cited briefings per story; supports revision feedback."""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from newsroom.citations import citation_issues
from newsroom.llm import chat
from newsroom.models import MODEL, EditorialStory, WritingPacket, WrittenStory

SYSTEM_PROMPT = """\
You are a technical journalist writing for an AI engineering newsletter.

Write a concise briefing for the story based on the provided angle:
- Length: 150–250 words
- Lead with the most important fact for engineers
- Follow the editorial angle
- End with a "Why it matters" sentence for practitioners
- Include inline citations as [Source Name](url) markdown links

When revision instructions are provided, address every issue raised while preserving what works.

Respond with ONLY a JSON object:
{
  "full_briefing": "<markdown text>",
  "sources_json": [{"name": "Source Name", "url": "https://..."}]
}"""


def _write_one(
    client: anthropic.Anthropic,
    story: EditorialStory,
    feedback: dict[str, str] | None,
    revision_number: int,
) -> WritingPacket:
    user_parts = [
        json.dumps(
            {
                "title": story["title"],
                "url": story["url"],
                "summary": story["summary"],
                "source_name": story["source_name"],
                "angle": story["angle"],
                "topic_tags": story["topic_tags"],
                "verification_caveats": story["verification_caveats"],
                "supporting_sources": story["supporting_sources"],
                "source_evidence": [
                    {
                        **source,
                        "evidence_text": source["evidence_text"][:3000],
                    }
                    for source in story["evidence_sources"]
                ],
            },
            indent=2,
        )
    ]

    if feedback and story["url"] in feedback:
        user_parts.append(f"\nRevision instructions:\n{feedback[story['url']]}")

    msg = chat(
        client,
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())

    written_story = WrittenStory(
            **story,
            full_briefing=parsed.get("full_briefing", ""),
            sources_json=[
                source
                for source in parsed.get("sources_json", [])
                if source in story["supporting_sources"]
            ]
            or story["supporting_sources"],
        )
    issues = citation_issues(written_story)
    if issues:
        raise ValueError(" ".join(issues))

    return WritingPacket(
        story=written_story,
        revision_number=revision_number,
    )


def run(
    stories: list[EditorialStory],
    feedback: dict[str, str] | None = None,
    revision_number: int = 0,
) -> list[WritingPacket]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_write_one, client, s, feedback, revision_number): s
            for s in stories
        }
        results: dict[str, WritingPacket] = {}
        for future in as_completed(futures):
            story = futures[future]
            try:
                packet = future.result()
                results[story["url"]] = packet
            except Exception as exc:
                # keep story moving with empty briefing rather than crash
                results[story["url"]] = WritingPacket(
                    story=WrittenStory(
                        **story,
                        full_briefing=f"[Writing error: {exc}]",
                        sources_json=[],
                    ),
                    revision_number=revision_number,
                )

    # return in original order
    return [results[s["url"]] for s in stories if s["url"] in results]
