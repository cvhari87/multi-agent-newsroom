# Multi-Agent Newsroom

A Python project that produces a daily AI engineering briefing using a **parent Newsroom Editor** and five **specialized child agents** built on Claude. Stories are fetched from RSS, verified, ranked, written, evaluated, and published — with a parent agent controlling every editorial decision. A FastAPI backend and React dashboard let you trigger runs and browse results in a browser.

---

## How it works

```
RSS Feeds → Research → Verification → Editorial → Writing → Evaluation → Output
                              ↑                         ↑
                      Parent Editor reviews        Parent Editor reviews
                      (accept / reject)            (approve / revise / reject)
```

The **Newsroom Editor** (parent) is the only agent that makes decisions. The five children do specialist work and return structured results. The parent reviews each stage before passing work forward. Stories that fail evaluation can be sent back to Writing for up to two revisions before being rejected.

---

## Pipeline stages

| Stage | Agent | What it does |
|-------|-------|--------------|
| 1 | **Research** | Fetches 5 RSS feeds, downloads article text, summarizes each story via Claude |
| 2 | **Verification** | Scores confidence (0–1), detects cross-source coverage, flags caveats |
| 3 | **Editor review** | Parent accepts or rejects each verified story |
| 4 | **Editorial** | Selects up to 8 stories, assigns topic tags and editorial angle |
| 5 | **Writing** | Drafts 150–250 word briefing per story with inline citations (concurrent, 4 workers) |
| 6 | **Evaluation** | Scores each draft 0–10, checks citations, recommends approve / revise / reject |
| 7 | **Editor review** | Parent approves (≥ 7.0), requests revision (≥ 5.0), or rejects (< 5.0); max 2 revisions |
| 8 | **Output** | Writes `output/briefing-YYYY-MM-DD.md`, persists stories to SQLite |

---

## RSS sources

| Feed | Publisher |
|------|-----------|
| [The Batch](https://www.deeplearning.ai/the-batch/feed/) | DeepLearning.AI |
| [Import AI](https://importai.substack.com/feed) | Jack Clark |
| [Hacker News AI](https://hnrss.org/newest?q=AI+engineering&points=50) | HN (≥ 50 points) |
| [The Gradient](https://thegradient.pub/rss/) | The Gradient |
| [Ahead of AI](https://magazine.sebastianraschka.com/feed) | Sebastian Raschka |

Up to 10 articles per feed, deduplicated by URL.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Agent model | Claude `claude-sonnet-4-6` (all agents) |
| Agent SDK | `anthropic` Python SDK |
| Backend API | FastAPI + Uvicorn |
| Frontend | React 19 + Vite |
| Database | SQLite (`newsroom.db`, zero setup) |
| RSS parsing | `feedparser` |
| HTTP client | `httpx` |
| Tests | `pytest` |
| Linter | `ruff` |

---

## Setup

**Requires Python 3.11+ and Node 18+.**

### 1. Clone and configure

```bash
git clone https://github.com/cvhari87/multi-agent-newsroom
cd multi-agent-newsroom
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Python backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                           # 17 tests should pass
```

### 3. Frontend

```bash
cd frontend
npm install
```

---

## Run

### Option A — CLI (headless)

```bash
newsroom
```

Runs the full pipeline and writes `output/briefing-YYYY-MM-DD.md`. No browser needed.

### Option B — Web dashboard

**Terminal 1** — start the API server:

```bash
uvicorn newsroom.api:app --reload --port 8000
```

**Terminal 2** — start the Vite dev server:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in a browser. Click **▶ New Run** to trigger the pipeline. Stories appear as cards you can filter by topic tag. Click any card for the full briefing with citations.

### Option C — Production build

```bash
cd frontend && npm run build
uvicorn newsroom.api:app --port 8000
```

The API serves the compiled frontend from `frontend/dist/` automatically. One process, one port.

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/run` | Trigger a pipeline run. Returns `202 { run_id, status: "running" }`. Rejects concurrent runs. |
| `GET` | `/api/runs` | All runs, newest first |
| `GET` | `/api/stories` | Story cards from the latest completed run. Supports `?tag=Agents` and `?run_id=uuid` |
| `GET` | `/api/stories/{id}` | Full story: briefing, citations, QC notes, scores. Returns 404 if not found |

---

## Topic tags

The Editorial agent assigns each story one or more tags from a fixed set:

`LLMs` · `Tooling` · `Infrastructure` · `Research` · `Safety` · `Agents` · `Data` · `Benchmarks` · `Open Source` · `Industry`

---

## Project layout

```
multi-agent-newsroom/
├── src/newsroom/
│   ├── orchestrator.py      # 8-stage pipeline controller
│   ├── editor.py            # Newsroom Editor (parent agent)
│   ├── models.py            # TypedDicts for each pipeline stage
│   ├── api.py               # FastAPI endpoints
│   ├── db.py                # SQLite schema + read/write helpers
│   ├── citations.py         # Deterministic citation validator
│   ├── structured.py        # JSON parse + validation helpers
│   ├── cli.py               # `newsroom` CLI entry point
│   └── agents/
│       ├── research.py      # Fetch + summarize RSS stories
│       ├── verification.py  # Confidence scoring + cross-source check
│       ├── editorial.py     # Story selection + angle assignment
│       ├── writing.py       # Draft briefings with citations
│       ├── evaluation.py    # Score + critique drafts
│       └── output.py        # Write Markdown + persist to SQLite
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root component + run trigger + polling
│   │   ├── api.js           # HTTP client (4 functions)
│   │   └── components/
│   │       ├── StoryCard.jsx
│   │       ├── StoryDetail.jsx
│   │       ├── TagFilter.jsx
│   │       └── RunHistory.jsx
│   └── package.json
├── tests/                   # pytest suite (17 tests)
├── docs/
│   └── architecture.md      # Full architecture reference
├── output/                  # Generated briefings (gitignored)
├── newsroom.db              # SQLite database (gitignored)
└── pyproject.toml
```

---

## Output format

Each approved story is written to `output/briefing-YYYY-MM-DD.md` in this structure:

```markdown
## Story Title

**Source:** example.com · **Tags:** LLMs, Research · **Eval:** 8.2/10
**Angle:** Why this matters for production ML teams

Briefing text with [inline citations](https://source.example.com)...

**Sources:** [Name](url), [Name](url)
```

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full parent-child design, data flow, SQLite schema, and design principles.
