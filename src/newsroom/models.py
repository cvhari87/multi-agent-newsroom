"""Shared data models — TypedDicts for agent handoffs and parent-child packets."""

from typing import TypedDict

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Story progression — each stage extends the previous
# ---------------------------------------------------------------------------

class RawStory(TypedDict):
    title: str
    url: str
    summary: str
    published_at: str
    source_name: str
    evidence_text: str
    evidence_status: str


class VerifiedStory(RawStory):
    confidence_score: float
    cross_source_count: int
    supporting_sources: list[dict[str, str]]
    evidence_sources: list[dict[str, str]]
    verification_caveats: list[str]


class EditorialStory(VerifiedStory):
    angle: str
    topic_tags: list[str]
    rank: int


class WrittenStory(EditorialStory):
    full_briefing: str
    sources_json: list[dict]


class EvaluatedStory(WrittenStory):
    eval_score: float
    eval_notes: str


# ---------------------------------------------------------------------------
# Child → Parent result packets
# ---------------------------------------------------------------------------

class VerificationPacket(TypedDict):
    story: VerifiedStory
    recommendation: str   # "accept" | "research_more" | "reject"
    caveats: list[str]


class EditorialPacket(TypedDict):
    story: EditorialStory
    rationale: str


class WritingPacket(TypedDict):
    story: WrittenStory
    revision_number: int


class EvaluationPacket(TypedDict):
    story: EvaluatedStory
    recommendation: str   # "approve" | "revise" | "reject"
    issues: list[str]


# ---------------------------------------------------------------------------
# Parent → Child decision
# ---------------------------------------------------------------------------

class ParentDecision(TypedDict):
    url: str
    action: str    # "accept"|"reject"  or  "approve"|"revise"|"reject"
    reason: str
    feedback: str  # revision instructions; empty string when not a revision
