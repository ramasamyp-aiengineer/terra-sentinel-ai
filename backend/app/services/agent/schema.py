"""Work-order schema.

Design principle: the *evidence* section is built deterministically from tool
data and is never written by an LLM. Gemini only writes the narrative fields
(summary, mechanism hypothesis, recommended action, site-specific checks), and
those are validated against the tool data before they are shown.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceLine(BaseModel):
    label: str
    value: str
    source: str  # which tool / record it came from


class ChecklistItem(BaseModel):
    item: str
    why: str | None = None


class Narrative(BaseModel):
    """The only fields an LLM is allowed to author."""

    summary: str = Field(description="2-3 plain-language sentences for a control-room officer.")
    mechanism_hypothesis: str = Field(description="Possible mechanism, explicitly worded as a hypothesis.")
    recommended_action: str = Field(description="What the engineer/crew should do and by when.")
    site_specific_checks: list[str] = Field(default_factory=list, description="Up to 3 extra field checks.")


class Validation(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    numbers_checked: int = 0


class WorkOrder(BaseModel):
    ticket_id: str
    site_id: str
    tier: str
    priority_label: str
    asset_name: str
    chainage: str
    lat: float
    lon: float
    as_of: str
    data_source: str
    consequence: str
    evidence: list[EvidenceLine]
    outlook_text: str
    summary: str
    mechanism_hypothesis: str
    recommended_action: str
    checklist: list[ChecklistItem]
    limitations: list[str]
    citations: list[str]
    generated_by: str  # "gemini" | "template"
    model: str | None = None
    validation: Validation
    tool_calls: list[dict] = Field(default_factory=list)
