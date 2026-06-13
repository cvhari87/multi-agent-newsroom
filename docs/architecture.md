# Architecture

## Overview

Multi-Agent Newsroom is a parent-child multi-agent system. One **Newsroom Editor** (parent) controls the pipeline and makes all editorial decisions. Five **child agents** do specialist work: Research, Verification, Editorial, Writing, and Evaluation. A deterministic **Output service** publishes approved stories.

Children do not call each other and cannot publish directly. Every handoff goes through the parent, which keeps delegation, retries, and final accountability in one place.

---

## High-level data flow

```
User / CLI / POST /api/run
          │
          ▼
    Orchestrator (orchestrator.py)
          │
          ├─► Research Child ──────────────────► list[RawStory]
          │                                            │
          ├─► Verification Child ◄─────────────────── │
          │        │                                   │
          │        └─► list[VerificationPacket]        │
          │                   │                        │
          ├─► Parent: review_verification()            │
          │        │  accept / reject per story        │
          │        ▼                                   │
          ├─► Editorial Child ─────────────────► list[EditorialPacket]  (max 8)
          │                                            │
          ├─► Writing Child (×4 concurrent) ◄──────── │
          │        │                                   │
          │        └─► list[WritingPacket]             │
          │                   │                        │
          ├─► Evaluation Child (concurrent) ◄───────── │
          │        │                                   │
          │        └─► list[EvaluationPacket]          │
          │                   │                        │
          ├─► Parent: review_evaluation()              │
          │        │  approve / revise / reject        │
          │        │  (max 2 revisions per story)      │
          │        ▼                                   │
          └─► Output Service ──────────────────► briefing.md + SQLite
```

---

## Agents

### Newsroom Editor (parent)

**File:** `src/newsroom/editor.py`  
**Model:** `claude-sonnet-4-6`

The parent makes two types of decisions:

| Method | When called | Decision |
|--------|-------------|----------|
| `review_verification()` | After Verification | Accept or reject each story (`confidence >= 0.5` + relevance) |
| `review_evaluation()` | After Evaluation | Approve (score ≥ 7.0), revise (≥ 5.0), or reject (< 5.0) |

Configuration:
- `MAX_REVISIONS = 2` — maximum revision cycles per story
- `PASS_SCORE = 7.0` — minimum eval score to approve

Parent rules:
- Never invents evidence or silently repairs unsupported claims
- Never passes unvalidated child output to another child
- Loads full artifacts only when a specific decision requires them
- Prefers partial success: publishes approved stories even if some stories fail
- Fails the run only when no publishable stories remain

---

### Research Child

**File:** `src/newsroom/agents/research.py`  
**Model:** `claude-sonnet-4-6`

Fetches and summarizes RSS stories.

**RSS feeds (hardcoded):**

| Feed | URL |
|------|-----|
| The Batch | `https://www.deeplearning.ai/the-batch/feed/` |
| Import AI | `https://importai.substack.com/feed` |
| Hacker News AI | `https://hnrss.org/newest?q=AI+engineering&points=50` |
| The Gradient | `https://thegradient.pub/rss/` |
| Ahead of AI | `https://magazine.sebastianraschka.com/feed` |

**Process:**
1. Fetch all 5 feeds concurrently (`ThreadPoolExecutor`)
2. Download article HTML for each link (`httpx`, 8 s timeout, 6000 char limit)
3. Summarize each article via Claude (8 concurrent workers)
4. Deduplicate by URL
5. Set `evidence_status` to `article_fetched` or `rss_fallback`

**Output:** `list[RawStory]` (max 10 per feed)

---

### Verification Child

**File:** `src/newsroom/agents/verification.py`  
**Model:** `claude-sonnet-4-6`

Scores confidence and detects cross-source coverage.

**Process:**
1. Sends all candidate stories as JSON to Claude in one call
2. Claude returns per-story: `confidence_score` (0–1), `supporting_urls`, `recommendation`, `caveats`
3. Cross-references `supporting_urls` against other stories in the set
4. Builds `VerifiedStory` with `cross_source_count` and `evidence_sources`

**Output:** `list[VerificationPacket]` with `{story, recommendation, caveats}`

**Recommendations:** `accept` · `research_more` · `reject`

---

### Editorial Child

**File:** `src/newsroom/agents/editorial.py`  
**Model:** `claude-sonnet-4-6`

Selects and frames the most useful stories for AI engineers.

**Process:**
1. Receives all parent-accepted `VerifiedStory` objects
2. Claude selects up to 8 stories, assigns each:
   - `topic_tags` — one or more from the fixed tag set
   - `angle` — one-sentence editorial framing
   - `rank` — 1 = most important
3. Parses JSON or Markdown-fenced output

**Topic tags (fixed set):** `LLMs` · `Tooling` · `Infrastructure` · `Research` · `Safety` · `Agents` · `Data` · `Benchmarks` · `Open Source` · `Industry`

**Output:** `list[EditorialPacket]` (max 8 stories)

---

### Writing Child

**File:** `src/newsroom/agents/writing.py`  
**Model:** `claude-sonnet-4-6`

Drafts cited briefings for each selected story.

**Process:**
1. Writes 150–250 words per story using the assigned angle and evidence
2. Returns JSON: `{ full_briefing, sources_json: [{name, url}] }`
3. Runs citation validation deterministically (`citations.py`)
4. Accepts optional `revision_feedback` from the parent on retry
5. Runs 4 stories concurrently (`ThreadPoolExecutor`)

**Output:** `list[WritingPacket]`

---

### Evaluation Child

**File:** `src/newsroom/agents/evaluation.py`  
**Model:** `claude-sonnet-4-6`

Critiques drafts independently before publication.

**Process:**
1. Claude evaluates each briefing: `eval_score` (0–10), `recommendation`, `issues`
2. Deterministic citation check (via `citations.py`) is applied on top:
   - No citations → score capped at 4.0
   - Broken citation URLs → score reduced
3. Final recommendation thresholds: approve ≥ 7.0, revise ≥ 5.0, reject < 5.0

**Output:** `list[EvaluationPacket]`

---

### Output Service

**File:** `src/newsroom/agents/output.py`  
**Not an LLM agent — deterministic only**

1. Writes `output/briefing-YYYY-MM-DD.md`
2. Inserts each story into `db.stories` (UUID per story)
3. Calls `db.complete_run()` with final metrics

---

## Deterministic services

These are code, not agents:

| Service | File | Purpose |
|---------|------|---------|
| Citation validator | `citations.py` | Extracts `[text](url)` links, checks all URLs exist in `supporting_sources` and `sources_json` |
| JSON parser | `structured.py` | Strips Markdown fences, parses JSON arrays, validates required fields |
| SQLite persistence | `db.py` | All reads and writes; source of truth for run state |
| FastAPI layer | `api.py` | Four REST endpoints; serves static frontend in production |
| CLI entry point | `cli.py` | `newsroom` command; runs full pipeline headless |

---

## Data models

Defined in `src/newsroom/models.py` as TypedDicts. Each stage extends the previous:

```
RawStory
  └── VerifiedStory     (+ confidence_score, cross_source_count, caveats)
        └── EditorialStory  (+ angle, topic_tags, rank)
              └── WrittenStory    (+ full_briefing, sources_json)
                    └── EvaluatedStory  (+ eval_score, eval_notes)
```

---

## SQLite schema

**Database file:** `newsroom.db` (created automatically at project root)

### `runs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `status` | TEXT | `running` · `complete` · `failed` |
| `started_at` | TEXT | ISO 8601 UTC |
| `finished_at` | TEXT | ISO 8601 UTC (nullable) |
| `story_count` | INTEGER | Approved stories published |
| `eval_score_avg` | REAL | Average eval score across approved stories |
| `briefing_path` | TEXT | Relative path to Markdown briefing |

### `stories`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `run_id` | TEXT FK | References `runs.id` |
| `title` | TEXT | Story headline |
| `url` | TEXT | Canonical article URL |
| `summary` | TEXT | Research-stage summary |
| `angle` | TEXT | Editorial angle (one sentence) |
| `full_briefing` | TEXT | Published briefing (Markdown) |
| `topic_tags` | TEXT | JSON array of tag strings |
| `sources_json` | TEXT | JSON array of `{name, url}` citation objects |
| `confidence_score` | REAL | Verification confidence (0–1) |
| `cross_source_count` | INTEGER | Number of corroborating sources |
| `eval_score` | REAL | Evaluation score (0–10) |
| `eval_notes` | TEXT | QC notes from Evaluation child |
| `published_at` | TEXT | ISO 8601 UTC |
| `created_at` | TEXT | ISO 8601 UTC |

### `run_events`

Audit trail of every pipeline stage transition, parent decision, and retry.

| Column | Type |
|--------|------|
| `id` | INTEGER PK |
| `run_id` | TEXT FK |
| `stage` | TEXT |
| `event` | TEXT |
| `details` | TEXT (JSON) |
| `created_at` | TEXT |

### `artifacts`

Complete stage outputs stored by reference so the parent prompt stays small.

| Column | Type |
|--------|------|
| `id` | TEXT PK (UUID) |
| `run_id` | TEXT FK |
| `stage` | TEXT |
| `payload` | TEXT (JSON) |
| `created_at` | TEXT |

---

## REST API

**File:** `src/newsroom/api.py`

| Method | Path | Behaviour |
|--------|------|-----------|
| `POST` | `/api/run` | Starts pipeline in background thread. Returns `202 {run_id, status}`. Rejects concurrent runs with `409`. |
| `GET` | `/api/runs` | All runs, newest first |
| `GET` | `/api/stories` | Story cards. `?run_id=uuid` to select a run; defaults to latest completed. `?tag=X` to filter by topic tag. |
| `GET` | `/api/stories/{id}` | Full story detail. Returns `404` if not found. |

CORS is enabled for `localhost:5173` and `localhost:3000` (Vite dev servers).  
In production the API serves `frontend/dist/` as static files.

---

## Frontend

**Stack:** React 19 + Vite 8

| File | Role |
|------|------|
| `App.jsx` | Root component: run trigger, polling, tag filter, story grid |
| `api.js` | Thin HTTP client wrapping the 4 API endpoints |
| `StoryCard.jsx` | Card grid item: title, summary, tags, eval score |
| `StoryDetail.jsx` | Full story view: briefing (Markdown → HTML), citations |
| `TagFilter.jsx` | Topic tag filter buttons |
| `RunHistory.jsx` | Collapsible table of past runs; click a row to load that run |

**Run trigger flow:**
1. User clicks **▶ New Run** → `POST /api/run`
2. Frontend polls `GET /api/stories` every 5 seconds
3. Stories appear when the run completes (max poll duration: 5 minutes)

---

## Concurrency model

Work within a pipeline stage runs concurrently; stages are sequential.

| Stage | Concurrency |
|-------|-------------|
| Research — fetch feeds | `ThreadPoolExecutor` (one thread per feed) |
| Research — summarize articles | `ThreadPoolExecutor` (8 workers) |
| Writing — draft briefings | `ThreadPoolExecutor` (4 workers) |
| Evaluation — score drafts | `ThreadPoolExecutor` (one per story) |
| API — pipeline trigger | `threading.Thread` + `Lock` (one active run at a time) |

---

## Failure and revision behaviour

| Condition | Action |
|-----------|--------|
| Verification confidence < 0.5 | Parent rejects story |
| Invalid JSON from child | Returned to same child for correction |
| Eval score < 5.0 | Story rejected; not retried |
| Eval score 5.0–6.9 | Sent back to Writing with specific notes (max 2 revisions) |
| Eval score ≥ 7.0 | Approved for publication |
| Article fetch fails | Falls back to RSS summary (`evidence_status: rss_fallback`) |
| One story fails | Other stories continue; partial success preferred |
| No stories approved | Run marked `failed` |

---

## Design principles

- **Parent owns every decision.** Children recommend; the parent decides.
- **Structured handoffs.** Every child returns typed, validated JSON.
- **Deterministic code for deterministic work.** Citation checking, deduplication, and persistence are never delegated to an LLM.
- **Artifacts by reference.** Complete stage outputs are stored in SQLite and referenced by ID. Parent prompts stay compact.
- **Auditable trail.** Every decision, retry, and rejection is recorded in `run_events`.
- **Partial success.** Failing stories are rejected individually; passing stories are published regardless.
- **Bounded retries.** Maximum 2 revisions per story; maximum 1 retry per transient tool failure.
