# Multi-Agent Newsroom — Spec

## Overview

A daily AI engineering news briefing produced by a parent-child multi-agent
system. A parent **Newsroom Editor** delegates bounded assignments to five
specialized child agents, reviews their structured results, requests revisions,
and makes the final publication decision. The final output is available as a
Markdown file and through a small web dashboard.

Narrow topic: daily AI engineering news.

Reference UI: https://www.mindstudio.ai/blog — article cards, topic tag filtering, clean reading view with citations.

---

## Parent-child agents

| Agent | Relationship | Role | Returns to parent |
|---|---|---|---|
| **Newsroom Editor** | Parent | Owns the run, delegates assignments, validates results, routes revisions, and approves publication | Final approval decisions and run audit trail |
| **Research** | Child | Collects candidate stories and source evidence from configured RSS and web sources | Candidate stories plus source and tool errors |
| **Verification** | Child | Checks support, groups related coverage, and identifies unsupported claims | Confidence, source agreement, caveats, and accept/research/reject recommendation |
| **Editorial** | Child | Ranks verified stories and selects useful angles | Ranked selections with `topic_tags[]`, angle, and rationale |
| **Writing** | Child | Produces a concise cited briefing for each selected story | Draft briefing with citations |
| **Evaluation** | Child | Independently checks support, citations, duplication, clarity, and relevance | Score, issue list, and approve/revise/reject recommendation |

Output and persistence are deterministic services called by the parent after
approval; they are not agents.

### Agent authority

- The parent is the only agent allowed to delegate, retry, reject, approve, or publish.
- Children act only on the assignment and evidence supplied by the parent.
- Children return structured artifacts and recommendations; they do not call one another.
- The parent routes an issue back to the child responsible for it.
- Complete artifacts are persisted in SQLite; the parent receives compact decision packets.
- Deterministic validators handle schemas, retry limits, and mechanical acceptance checks.
- The MVP allows at most two revisions per assignment.
- Stories scoring below `7.0` receive one Writing revision and are rejected if they still fail.

---

## Core loop (MVP)

```
POST /api/run
  → Parent Newsroom Editor creates the run and briefing goal
  → Parent delegates collection to Research child
  → Parent validates results and delegates verification
  → Parent delegates accepted stories to Editorial child
  → Parent delegates selected stories to Writing child
  → Parent delegates drafts to Evaluation child
  → Parent routes revisions or rejects stories
  → Parent approves passing stories
  → Deterministic output service writes briefing.md + persists to SQLite

GET /api/stories          → article grid (dashboard)
GET /api/stories?tag=X    → filtered by topic tag
GET /api/stories/{id}     → full briefing + citations
GET /api/runs             → past run history + status
```

User flow: trigger run → briefing.md written to disk (can open immediately) → open dashboard to browse article cards → filter by tag → read full briefing per story.

Research source fetches, per-story verification, writing, and evaluation run
concurrently where their dependencies allow. The parent is invoked per decision
with relevant summaries and artifact IDs, not the entire run history.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| Agent runtime | Parent-child orchestrator using Claude claude-sonnet-4-6 via `anthropic` SDK |
| Frontend | React + Vite |
| Data | SQLite (`newsroom.db`, local, zero setup) |
| RSS parsing | `feedparser` |
| Markdown output | Written to `output/briefing-{date}.md` |

Default sources (MVP — hardcoded):

1. The Batch (deeplearning.ai) — `https://www.deeplearning.ai/the-batch/feed/`
2. Import AI (Jack Clark) — `https://importai.substack.com/feed`
3. Hacker News AI tag — `https://hnrss.org/newest?q=AI+engineering&points=50`
4. The Gradient — `https://thegradient.pub/rss/`
5. Ahead of AI (Sebastian Raschka) — `https://magazine.sebastianraschka.com/feed`

---

## Data model

### `runs`
| Column | Type | Notes |
|---|---|---|
| id | TEXT (UUID) | Primary key |
| status | TEXT | `running`, `complete`, `failed` |
| started_at | TEXT (ISO 8601) | |
| finished_at | TEXT | Null until complete |
| story_count | INTEGER | Stories that passed evaluation |
| eval_score_avg | REAL | Average eval score across stories |
| briefing_path | TEXT | Path to generated `briefing-{date}.md` |

### `stories`
| Column | Type | Notes |
|---|---|---|
| id | TEXT (UUID) | Primary key |
| run_id | TEXT | Foreign key → runs.id |
| title | TEXT | |
| url | TEXT | Original source URL |
| summary | TEXT | Raw summary from RSS |
| angle | TEXT | Editorial agent's selected angle |
| full_briefing | TEXT | Markdown written by Writing agent |
| topic_tags | TEXT | JSON array e.g. `["LLMs","tooling"]` |
| sources_json | TEXT | JSON array of `{name, url}` citations |
| confidence_score | REAL | 0–1 from Verification agent |
| cross_source_count | INTEGER | How many sources mentioned it |
| eval_score | REAL | 0–10 from Evaluation agent |
| eval_notes | TEXT | Citation gaps, duplication flags |
| published_at | TEXT | Original publication date |
| created_at | TEXT | When persisted |

### `artifacts`
| Column | Type | Notes |
|---|---|---|
| id | TEXT (UUID) | Primary key |
| run_id | TEXT | Foreign key → runs.id |
| stage | TEXT | Producing child or revision stage |
| payload | TEXT | Complete JSON artifact |
| created_at | TEXT | When persisted |

### `run_events`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| run_id | TEXT | Foreign key → runs.id |
| stage | TEXT | Workflow stage or parent |
| event | TEXT | `started`, `completed`, `reviewed`, or `failed` |
| details | TEXT | Compact JSON decision packet or event details |
| created_at | TEXT | When persisted |

---

## API contract

### `POST /api/run`
Triggers the full agent pipeline. Runs in background; returns run ID immediately.

Response `202`:
```json
{ "run_id": "uuid", "status": "running" }
```

### `GET /api/runs`
Lists all runs, newest first.

Response `200`:
```json
{
  "runs": [
    { "id": "uuid", "status": "complete", "started_at": "...", "finished_at": "...", "story_count": 8, "eval_score_avg": 7.4, "briefing_path": "output/briefing-2026-06-12.md" }
  ]
}
```

### `GET /api/stories`
Stories from the most recent completed run. Optional filters: `?tag=LLMs`, `?run_id=uuid`.

Response `200`:
```json
{
  "stories": [
    { "id": "uuid", "title": "...", "summary": "...", "angle": "...", "topic_tags": ["LLMs"], "eval_score": 8.1, "source_count": 3, "published_at": "..." }
  ]
}
```

### `GET /api/stories/{id}`
Full story with briefing and citations.

Response `200`:
```json
{
  "id": "uuid",
  "title": "...",
  "angle": "...",
  "full_briefing": "Markdown...",
  "topic_tags": ["LLMs"],
  "sources": [{"name": "Import AI", "url": "https://..."}],
  "confidence_score": 0.87,
  "eval_score": 8.1,
  "eval_notes": ""
}
```

---

## Scope

### In MVP
- Parent Newsroom Editor with five specialist child agents
- Structured parent-to-child assignments and child-to-parent results
- Persisted workflow state and compact parent decision packets
- Concurrent per-source and per-story child assignments
- Bounded revision loop driven by the parent
- Research → Verification → Editorial → Writing → Evaluation delegation sequence
- Manual trigger via `POST /api/run` or dashboard button
- 5 hardcoded RSS sources
- Markdown briefing written to `output/briefing-{date}.md`
- SQLite persistence
- Article grid with topic tag filtering
- Story detail view with full briefing and citations
- Evaluation flags visible on low-score stories

### Excluded from MVP
- Scheduled / cron runs
- User accounts or authentication
- Custom source configuration UI
- Email or Telegram delivery
- Real-time pipeline progress streaming
- Full-text search
- Admin UI
