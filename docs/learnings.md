# Learnings

Lessons from building and running the multi-agent newsroom pipeline.

---

## 1. One giant prompt does not scale

**What happened:** The Verification agent sent all 36 stories in a single Claude call with 1500 chars of evidence per story (~54k chars total). Two concurrent runs hitting this simultaneously caused rate limiting and timeouts that stalled the pipeline for 13+ minutes.

**Fix:** Batch stories into groups of 12 and verify concurrently (up to 4 batches). Evidence per story trimmed from 1500 → 500 chars. Result: 3 concurrent calls of ~6k chars each instead of one massive call.

**Principle:** Size each LLM call for the reasoning task it actually needs, not the maximum context you have available. For scoring/classification tasks, 500 chars of evidence is sufficient. Save the full text for tasks that genuinely require it (Writing, Evaluation).

---

## 2. Parallelism within a stage is not the same as parallelism across the pipeline

**What we explored:** Adding more parallel paths across pipeline stages (Research → Verification → Editorial etc.).

**What we found:** The stages are sequentially dependent — you can't start Verification until Research finishes, can't start Writing until Editorial assigns angles. The only soft dependency is Writing → Evaluation (you could evaluate each story as soon as its draft is ready instead of waiting for all drafts).

**Fix applied:** Maximize concurrency within each stage instead:
- Research: parallel feed fetching + 8-worker summarization
- Verification: batched concurrent calls
- Writing: 4 concurrent workers
- Evaluation: concurrent per story

**Principle:** Map your dependency graph before adding parallelism. Hard dependencies between stages cannot be parallelized without fundamentally redesigning the workflow. Soft dependencies (like Writing → Evaluation) can be pipelined but add complexity — measure whether the gain justifies it before building it.

---

## 3. Rate limit errors need to be handled, not ignored

**What happened:** Concurrent pipeline runs both calling Claude triggered 429 (rate limit) and 529 (overloaded) errors, crashing runs mid-pipeline.

**Fix:** Centralized `chat()` wrapper in `llm.py` with exponential backoff (2s → 4s → 8s → 16s + jitter, max 4 retries) applied to all six Claude callers. Only retries on 429/529; all other errors propagate immediately.

**Principle:** In any system making many concurrent API calls, rate limit handling is not optional. Centralizing it in one wrapper means you fix it once and every caller benefits. Don't handle it inline per agent — you'll miss some and handle others inconsistently.

---

## 4. Filter early, not late

**What happened:** All RSS articles — including off-topic HN posts that slipped through the `points>=50` filter — were passed to Verification, which spent tokens scoring articles that had no chance of making the briefing.

**Fix:** Keyword filter in Research after enrichment. Articles whose title + summary contain no AI/ML-related terms are dropped before they reach Verification. Also capped stories sent to Editorial at the top 20 by confidence score — Editorial only picks 8, so sending 30+ was pure waste.

**Principle:** Every downstream agent inherits the noise of every upstream agent. Filtering at the earliest possible stage reduces token spend, latency, and error surface in all subsequent stages. A cheap deterministic filter beats an expensive LLM filter for high-recall, low-precision tasks like topic relevance.

---

## 5. Deterministic code is more reliable than LLM code for deterministic tasks

**What we built:** Citation validation (`citations.py`) is entirely deterministic — extract `[text](url)` links, check they exist in `supporting_sources` and `sources_json`. It runs on every draft from Writing and caps Evaluation scores when citations fail.

**Why it matters:** Early versions delegated citation checking to the Evaluation agent. It was inconsistent — sometimes it caught missing citations, sometimes it didn't. Moving this to deterministic code made citation enforcement reliable and fast.

**Principle:** Identify which parts of your pipeline have objectively correct answers (URL existence, JSON schema validity, deduplication, field presence). Implement those as code, not prompts. Reserve LLMs for tasks that genuinely require judgment: relevance, quality, tone, angle selection.

---

## 6. The parent agent's context budget matters

**What we designed:** The Newsroom Editor (parent) never holds the full run history or all artifacts in its prompt. Artifacts are stored in SQLite and referenced by ID. The orchestrator builds compact decision packets — only the scores, recommendations, and blocking issues — before invoking the parent.

**Why it matters:** A parent agent that accumulates full drafts, full verification results, and full evaluation outputs across 8 stories and 2 revision cycles would quickly exceed useful context lengths and become expensive. Compact packets keep parent calls fast and cheap.

**Principle:** Design the parent's prompt as if it were a manager receiving a one-page briefing, not a developer reading raw logs. The parent needs the decision-relevant summary, not the full artifact.

---

## 7. RSS-only pipelines are limited by feed quality

**What we found:** The five hardcoded feeds vary significantly in signal quality:
- The Batch, Import AI, Ahead of AI: consistently high signal, structured content
- The Gradient: good but lower frequency
- Hacker News AI: high noise — the `points>=50` filter helps but off-topic posts still slip through

**Implication:** The pruning filter matters most for HN. A future improvement would be feed-specific confidence priors — stories from The Batch start with higher assumed credibility than HN stories.

---

## 8. `MAX_PER_FEED` is the most effective speed lever

**What we observed:** Research is the longest stage — it fetches and summarizes up to 50 articles (10 per feed × 5 feeds) with 8 concurrent Claude calls. Downstream optimizations (batching, capping, pruning) reduce load on later stages but can't compress Research time.

**The lever:** Reducing `MAX_PER_FEED` from 10 to 5-6 roughly halves Research and Verification time. The tradeoff is fewer candidate stories, which may affect final briefing quality if the top stories happen to be beyond the cut.

**Principle:** Identify which stage sets the floor for total pipeline time. Optimize there first. In this pipeline, Research is that stage.

---

## 9. Partial success is better than all-or-nothing

**What we designed:** If one story fails writing or evaluation, it is rejected individually. Other stories continue unaffected. The run only fails completely if no publishable stories remain.

**Why it matters:** Early versions failed the entire run if any child threw an exception. A single paywalled article causing a fetch error would abort 7 good stories.

**Principle:** In multi-step pipelines processing independent items, failure should be scoped to the item, not the run. Build explicit rejection paths so one bad story doesn't block good ones.

---

## 10. SQLite is the right persistence choice for a local single-node pipeline

**Why it works here:** Zero setup, no network dependency, fast enough for the write volume (one run = ~50 inserts), supports concurrent reads from the API while the pipeline writes. The schema (runs, stories, artifacts, run_events) gives a complete audit trail without operational overhead.

**When it would break:** Multiple simultaneous pipeline runs writing to the same db file at high frequency, or deploying across multiple machines. At that point, PostgreSQL or a cloud DB makes more sense. The `threading.Lock` in `api.py` prevents concurrent runs for now, which keeps SQLite safe.

**Principle:** Match your persistence choice to your actual deployment topology. A local dev tool with one active run at a time doesn't need a managed database.
