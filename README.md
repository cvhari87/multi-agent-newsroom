# Multi-Agent Newsroom

A bootcamp project that produces a trustworthy daily AI engineering briefing
using a parent Newsroom Editor and specialized child agents.

## Workflow

1. The parent delegates evidence collection to the Research child.
2. The Verification child checks supplied evidence and source agreement.
3. The parent reviews verification and delegates accepted stories to Editorial.
4. Writing children draft selected stories concurrently.
5. Evaluation children check citations, duplication, and quality.
6. The parent requests revisions or approves publication.
7. Deterministic output code publishes the approved briefing.

## Scope

- Focus: daily AI engineering news
- Input: 5 hardcoded RSS feeds (The Batch, Import AI, HN AI, The Gradient, Ahead of AI)
- Output: a cited Markdown briefing + web dashboard
- Parent-controlled approval before final publication

## Setup

### Backend

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                        # 17 tests should pass
```

### Frontend

```bash
cd frontend
npm install
```

## Run

### Option 1 — CLI (headless)

```bash
newsroom
```

Runs the full pipeline and writes `output/briefing-{date}.md`.

### Option 2 — Web dashboard

Start the API server:

```bash
uvicorn newsroom.api:app --reload --port 8000
```

Start the Vite dev server (in a second terminal):

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 — click **▶ New Run** to trigger the pipeline, then
browse article cards, filter by topic tag, and read full briefings with citations.

### Production build

```bash
cd frontend && npm run build
uvicorn newsroom.api:app --port 8000
```

The API serves the built frontend from `frontend/dist/` automatically.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/run` | Trigger a new pipeline run (returns 202) |
| `GET` | `/api/runs` | List all runs, newest first |
| `GET` | `/api/stories` | Stories from latest completed run (`?tag=X`, `?run_id=X`) |
| `GET` | `/api/stories/{id}` | Full story with briefing and citations |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.11+) |
| Agent runtime | Parent-child orchestrator using Claude claude-sonnet-4-6 via `anthropic` SDK |
| Frontend | React + Vite |
| Data | SQLite (`newsroom.db`, local, zero setup) |
| RSS parsing | `feedparser` |
| Markdown output | Written to `output/briefing-{date}.md` |
