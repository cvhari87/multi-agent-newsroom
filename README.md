# Multi-Agent Newsroom

A bootcamp project that produces a trustworthy daily AI engineering briefing
using a parent Newsroom Editor and specialized child agents.

## Proposed Workflow

1. The parent delegates evidence collection to the Research child.
2. The Verification child checks supplied evidence and source agreement.
3. The parent reviews verification and delegates accepted stories to Editorial.
4. Writing children draft selected stories concurrently.
5. Evaluation children check citations, duplication, and quality.
6. The parent requests revisions or approves publication.
7. Deterministic output code publishes the approved briefing.

## Initial Scope

- Focus: daily AI engineering news
- Input: a small configured list of RSS feeds and web sources
- Output: a cited Markdown briefing
- Parent-controlled approval before final publication

## Setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Run

```bash
newsroom
```

The command runs the complete parent-child newsroom pipeline.
