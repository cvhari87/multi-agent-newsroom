"""Research child — collects stories and preserves source evidence."""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import feedparser
import httpx

from newsroom.llm import chat
from newsroom.models import FAST_MODEL, RawStory

_AI_KEYWORDS = {
    "ai", "ml", "llm", "gpt", "claude", "gemini", "model", "neural",
    "machine learning", "deep learning", "training", "inference",
    "transformer", "benchmark", "dataset", "fine-tun", "rag", "agent",
    "embedding", "diffusion", "gpu", "cuda", "foundation model",
    "language model", "generative", "openai", "anthropic", "mistral",
    "llama", "hugging face",
}


def _is_ai_relevant(story: RawStory) -> bool:
    text = f"{story['title']} {story['summary']}".lower()
    return any(kw in text for kw in _AI_KEYWORDS)

SOURCES: list[tuple[str, str]] = [
    ("The Batch",    "https://www.deeplearning.ai/the-batch/feed/"),
    ("Import AI",    "https://importai.substack.com/feed"),
    ("Hacker News AI", "https://hnrss.org/newest?q=AI+engineering&points=50"),
    ("The Gradient", "https://thegradient.pub/rss/"),
    ("Ahead of AI",  "https://magazine.sebastianraschka.com/feed"),
]

MAX_PER_FEED = 6
FETCH_TIMEOUT = 8
MAX_ARTICLE_CHARS = 6000

SUMMARIZE_SYSTEM = """\
You are a research assistant for an AI engineering newsletter.

Given an article, write a 2-3 sentence factual summary that captures:
- The specific model, method, benchmark, or announcement involved
- The key result or claim
- Why it matters to AI engineers

Return the summary only — no preamble, no labels."""


def _fetch_article_text(url: str) -> str | None:
    try:
        resp = httpx.get(
            url,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "newsroom-bot/1.0"},
        )
        if resp.status_code == 200:
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:MAX_ARTICLE_CHARS]
    except Exception:
        pass
    return None


def _fetch_feed(source: tuple[str, str]) -> list[RawStory]:
    source_name, feed_url = source
    try:
        response = httpx.get(
            feed_url,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "newsroom-bot/1.0"},
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception:
        return []

    stories: list[RawStory] = []
    for entry in feed.entries[:MAX_PER_FEED]:
        link = entry.get("link", "")
        if not link:
            continue
        summary = entry.get("summary", "") or entry.get("description", "")
        if "<" in summary:
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
        stories.append(
            RawStory(
                title=entry.get("title", "Untitled")[:200],
                url=link,
                summary=summary[:1000],
                published_at=entry.get("published", "") or entry.get("updated", ""),
                source_name=source_name,
                evidence_text="",
                evidence_status="pending",
            )
        )
    return stories


def _summarize(client: anthropic.Anthropic, story: RawStory, text: str) -> str:
    msg = chat(
        client,
        model=FAST_MODEL,
        max_tokens=256,
        system=SUMMARIZE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Title: {story['title']}\nSource: {story['source_name']}\n\n{text}",
            }
        ],
    )
    return msg.content[0].text.strip()


def _enrich(client: anthropic.Anthropic, story: RawStory) -> RawStory:
    article_text = _fetch_article_text(story["url"])
    if not article_text:
        return RawStory(
            **{
                **story,
                "evidence_text": story["summary"],
                "evidence_status": "rss_fallback",
            }
        )

    return RawStory(
        **{
            **story,
            "summary": _summarize(client, story, article_text),
            "evidence_text": article_text,
            "evidence_status": "article_fetched",
        }
    )


def run() -> list[RawStory]:
    # --- collect raw RSS entries concurrently ---
    seen_urls: set[str] = set()
    stories: list[RawStory] = []

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        feed_futures = [pool.submit(_fetch_feed, source) for source in SOURCES]
        for future in as_completed(feed_futures):
            for story in future.result():
                if story["url"] in seen_urls:
                    continue
                seen_urls.add(story["url"])
                stories.append(story)

    # --- summarize each article in parallel ---
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"     Enriching {len(stories)} articles…")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_enrich, client, s): s for s in stories}
        enriched: list[RawStory] = []
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
                enriched.append(result)
                print(f"     {done}/{len(stories)} enriched ({result['evidence_status']}): {result['title'][:60]}", flush=True)
            except Exception:
                original = futures[future]
                enriched.append(
                    RawStory(
                        **{
                            **original,
                            "evidence_text": original["summary"],
                            "evidence_status": "rss_fallback",
                        }
                    )
                )
                print(f"     {done}/{len(stories)} enriched (fallback): {original['title'][:60]}", flush=True)

    # --- prune articles that aren't AI-relevant ---
    before = len(enriched)
    enriched = [s for s in enriched if _is_ai_relevant(s)]
    pruned = before - len(enriched)
    if pruned:
        print(f"     Pruned {pruned} non-AI articles before verification")

    return enriched
