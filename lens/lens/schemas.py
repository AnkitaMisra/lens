"""
schemas.py — Lens Pydantic schemas
CCA Domain 3: Structured output + validation

All agent inputs and outputs are validated against these schemas.
Nullable fields prevent hallucination — if data isn't in the source,
return None rather than inventing a plausible value.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ─── Research goal ────────────────────────────────────────────────

class ResearchGoal(BaseModel):
    """Input to the coordinator."""
    project_id: str
    goal: str
    session_id: str | None = None

    @field_validator("goal")
    @classmethod
    def goal_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Research goal cannot be empty")
        if len(v.strip()) < 10:
            raise ValueError("Research goal is too vague — please be more specific")
        return v.strip()


# ─── Provenance envelope ──────────────────────────────────────────

class ProvenanceEnvelope(BaseModel):
    """
    Wraps every agent output before passing downstream.
    The coordinator creates this — never the agents themselves.
    This is how the final report traces every claim to its source.
    """
    source_agent: Literal["SearchAgent", "DocumentAgent", "AnalyserAgent", "WriterAgent"]
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    content: Any


# ─── Search agent schemas ─────────────────────────────────────────

class SearchResult(BaseModel):
    """Single result from a web search."""
    title: str
    url: str
    snippet: str
    published_date: str | None = None    # nullable — not always available
    credibility_signal: str | None = None # nullable — may not be assessable


class SearchAgentOutput(BaseModel):
    """Validated output from SearchAgent."""
    query: str
    results: list[SearchResult]
    total_found: int

    @field_validator("results")
    @classmethod
    def at_least_one_result(cls, v: list) -> list:
        # Empty results are valid — source may have no results
        return v


# ─── Document agent schemas ───────────────────────────────────────

class ExtractedClaim(BaseModel):
    """A specific claim extracted from a document."""
    claim: str
    quote: str | None = None           # nullable — direct quote if available
    section: str | None = None         # nullable — document section if known
    confidence: Literal["high", "medium", "low"]


class DocumentAgentOutput(BaseModel):
    """Validated output from DocumentAgent."""
    url: str
    title: str
    summary: str
    claims: list[ExtractedClaim]
    word_count: int | None = None      # nullable — may not be extractable
    published_date: str | None = None  # nullable — may not be present
    author: str | None = None          # nullable — may not be listed


# ─── Analyser agent schemas ───────────────────────────────────────

class Conflict(BaseModel):
    """A detected conflict between two sources."""
    claim_a: str
    source_a: str                      # URL or document title
    claim_b: str
    source_b: str
    conflict_description: str
    severity: Literal["high", "medium", "low"]


class AnalyserAgentOutput(BaseModel):
    """Validated output from AnalyserAgent."""
    goal: str
    key_findings: list[str]            # Top findings across all sources
    conflicts: list[Conflict]          # Empty list = no conflicts found
    confidence: Literal["high", "medium", "low"]
    gaps: list[str]                    # Areas where research is insufficient
    sources_analysed: int


# ─── Writer agent schemas ─────────────────────────────────────────

class WriterAgentOutput(BaseModel):
    """Validated output from WriterAgent."""
    title: str
    content_md: str                    # Full Markdown report
    word_count: int
    citation_count: int
    executive_summary: str             # 2-3 sentence summary

    @field_validator("content_md")
    @classmethod
    def report_has_content(cls, v: str) -> str:
        if len(v.strip()) < 100:
            raise ValueError("Report content is too short — minimum 100 characters")
        return v

    @field_validator("executive_summary")
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Executive summary cannot be empty")
        return v.strip()


# ─── Session schemas ──────────────────────────────────────────────

class SessionCheckpoint(BaseModel):
    """State saved after every completed step."""
    session_id: str
    project_id: str
    goal: str
    current_step: str
    checkpoint_data: dict = Field(default_factory=dict)
    status: Literal["running", "paused", "complete", "failed"] = "running"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ─── Finding schema ───────────────────────────────────────────────

class Finding(BaseModel):
    """
    A research finding saved to the project workspace.
    contradicts_id links conflicting findings for the Analyser.
    embedding is populated by the MCP server for semantic search.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    session_id: str
    source_agent: str
    claim: str
    confidence: Literal["high", "medium", "low"]
    source_url: str | None = None      # nullable — internal findings have no URL
    contradicts_id: str | None = None  # nullable — most findings have no conflict
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ─── Error schemas ────────────────────────────────────────────────

class CoordinatorError(Exception):
    """
    Structured error from the coordinator.
    Includes enough context for the caller to decide how to handle it.
    """
    def __init__(
        self,
        message: str,
        session_id: str | None = None,
        step: str | None = None,
        agent: str | None = None,
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.session_id = session_id
        self.step = step
        self.agent = agent
        self.is_retryable = is_retryable

    def to_dict(self) -> dict:
        return {
            "error": True,
            "message": self.message,
            "session_id": self.session_id,
            "step": self.step,
            "agent": self.agent,
            "is_retryable": self.is_retryable,
        }
