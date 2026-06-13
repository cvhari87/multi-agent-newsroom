# Parent-Child Multi-Agent Architecture

## Overview

The system uses one parent agent, the **Newsroom Editor**, to manage a team of
specialized child agents. The parent owns the briefing goal and final decision.
Children receive bounded assignments, use only the tools needed for their role,
and return structured artifacts to the parent.

Children do not call one another or publish directly. This keeps delegation,
retries, and final accountability visible in one place.

The parent is a logical role, not one long-running conversation. Complete
artifacts and workflow state are persisted in SQLite. For each decision, the
orchestrator gives the parent only the relevant assignment, compact result
summary, scores, and blocking issues.

```text
User / POST /api/run
        |
        v
Parent: Newsroom Editor
        |
        +-- delegate --> Research Child
        |
        +-- delegate --> Verification Child
        |
        +-- delegate --> Editorial Child
        |
        +-- delegate --> Writing Child
        |
        +-- delegate --> Evaluation Child
        |
        +-- decide: publish, revise, reject, or fail run
        |
        v
Deterministic Output Service --> SQLite + Markdown
```

## Parent Agent: Newsroom Editor

The parent acts like an editor-in-chief and run orchestrator. It should reason
about what work is needed, delegate it, inspect results, and decide what happens
next. It should not perform every specialist task itself.

### Responsibilities

- Translate the run request into a briefing goal and constraints.
- Create assignments with explicit inputs, expected outputs, and acceptance criteria.
- Invoke children in the correct order and preserve their structured artifacts.
- Validate child outputs before passing them onward.
- Ask a child to revise work when acceptance criteria are not met.
- Reject unsupported or low-quality stories.
- Decide which evaluated stories are approved for publication.
- Record run status, decisions, failures, and retry reasons.
- Call the deterministic output service only after approval.

### Parent Rules

- Never invent evidence or silently repair unsupported claims.
- Never pass unvalidated free-form child output to another child.
- Never keep the full run history or every full artifact in its prompt.
- Load complete artifacts only when a decision specifically requires them.
- Give revision requests to the child responsible for the problem.
- Allow at most two revisions per assignment in the MVP.
- Prefer partial success: publish approved stories if one child task fails.
- Fail the run only when no publishable stories remain or a required service fails.

### Parent Decisions

| Child result | Parent action |
| --- | --- |
| Valid and meets acceptance criteria | Accept and delegate the next assignment |
| Structurally invalid | Retry the same child with validation errors |
| Missing evidence | Return to Research or Verification |
| Weak angle or poor story selection | Return to Editorial |
| Unsupported or unclear draft | Return to Writing with specific notes |
| Evaluation score below 7.0 | Request one Writing revision, then reject if still below 7.0 |
| Evaluation score at least 7.0 with valid citations | Approve for publication |

## Child Agents

Each child is a specialist worker. A child acts only on the assignment supplied
by the parent and returns a result plus enough metadata for the parent to judge
it. A child may recommend an action, but it cannot decide the overall workflow.

### Research Child

**Goal:** Find candidate stories and collect source evidence.

**Acts by:**

- Reading the configured RSS sources.
- Normalizing article metadata and removing exact URL duplicates.
- Returning candidate stories with source URLs and available summaries.
- Reporting source failures instead of hiding them.

**Must not:** rank stories, estimate facts it cannot observe, or select stories
for publication.

### Verification Child

**Goal:** Assess whether each candidate is sufficiently supported.

**Acts by:**

- Comparing candidate stories and grouping likely coverage of the same event.
- Assessing credibility using the supplied evidence.
- Returning confidence, source agreement, unsupported claims, and caveats.
- Recommending `accept`, `needs_research`, or `reject`.

**Must not:** fabricate cross-source coverage or rewrite the story.

### Editorial Child

**Goal:** Select and frame the most useful verified stories for AI engineers.

**Acts by:**

- Ranking only stories accepted by Verification.
- Selecting up to eight stories.
- Assigning topic tags and a specific editorial angle.
- Explaining briefly why each selected story matters.

**Must not:** introduce new factual claims or weaken verification caveats.

### Writing Child

**Goal:** Draft a concise, cited briefing for each selected story.

**Acts by:**

- Writing 150-250 words using the approved angle and evidence.
- Attaching citations to factual claims.
- Preserving uncertainty and caveats from Verification.
- Revising drafts in response to specific parent feedback.

**Must not:** use sources outside the assignment or publish directly.

### Evaluation Child

**Goal:** Critique drafts independently before publication.

**Acts by:**

- Checking factual support, citation coverage, clarity, duplication, and relevance.
- Returning a score from 0-10 and actionable issue list.
- Identifying which child should address each issue.
- Recommending `approve`, `revise`, or `reject`.

**Must not:** silently rewrite drafts or approve unsupported claims.

## Structured Delegation Contract

Every parent-to-child assignment uses the same envelope:

```json
{
  "run_id": "uuid",
  "task_id": "uuid",
  "child": "verification",
  "goal": "Verify the supplied candidate stories",
  "inputs": {},
  "constraints": [],
  "acceptance_criteria": [],
  "revision_number": 0
}
```

Every child-to-parent result uses this envelope:

```json
{
  "task_id": "uuid",
  "status": "complete",
  "artifact_ids": ["uuid"],
  "summary": "Two independent sources support the announcement.",
  "scores": {"confidence": 0.88},
  "recommendation": "accept",
  "issues": [],
  "tool_errors": []
}
```

Complete artifacts are persisted separately and referenced by ID. The parent
validates the compact result envelope and loads a complete artifact only when
needed for a decision.

## State and Context Management

SQLite is the source of truth for run state. The parent does not rely on chat
history as memory.

Persisted state includes:

- Runs, stage events, status transitions, and retry counts
- Complete child artifacts, including revision artifacts
- Parent decisions and reasons
- Scores, issues, citations, and tool failures

Before invoking the parent, deterministic code builds a compact decision packet:

```json
{
  "run_id": "uuid",
  "decision": "review_evaluation",
  "story_id": "uuid",
  "artifact_ids": ["draft-uuid", "evaluation-uuid"],
  "summary": "Draft scored 6.4 because two claims lack citations.",
  "recommendation": "revise",
  "blocking_issues": [
    {"owner": "writing", "issue": "Add citations for benchmark claims"}
  ]
}
```

This limits parent context, latency, and cost while preserving an auditable
parent-child workflow.

## Run Sequence

```text
1. Parent creates run and briefing goal.
2. Parent delegates collection to Research.
3. Parent validates candidates and delegates them to Verification.
4. Parent rejects unsupported candidates and delegates accepted stories to Editorial.
5. Parent validates selections and delegates each selected story to Writing.
6. Parent delegates each draft to Evaluation.
7. Parent routes actionable issues back to the responsible child.
8. Parent approves stories that pass evaluation.
9. Parent calls deterministic output and persistence services.
10. Parent completes the run with an audit trail of tasks and decisions.
```

The pipeline is ordered between stages, but work within a stage is concurrent:

- Fetch configured sources concurrently.
- Verify independent story clusters concurrently.
- Write selected stories concurrently.
- Evaluate each draft as soon as it completes.
- Publish approved stories after all active story tasks settle.

## Deterministic Services

These operations are tools or application services, not agents:

- RSS fetching and parsing
- Schema validation
- Exact URL deduplication
- Building compact parent decision packets
- Retry counting and task status transitions
- SQLite reads and writes
- Markdown rendering
- Citation URL validation
- API responses

## Failure and Revision Behavior

- A child returns tool failures in `tool_errors`; it does not conceal them.
- The parent retries transient tool failures once.
- Invalid structured output is returned to the same child for correction.
- Evaluation issues are routed to the child that owns the faulty artifact.
- The parent records every retry, rejection, and approval for the run.
- Exhausted retries reject the affected story rather than blocking unrelated stories.

## Design Principles

- Make parent-child delegation visible and auditable.
- Preserve source URLs and evidence throughout the workflow.
- Use structured handoffs between parent and children.
- Keep final editorial and publication decisions with the parent.
- Use deterministic code for deterministic work.
- Bound retries, token usage, and child authority.
- Persist workflow state instead of relying on parent conversation memory.
