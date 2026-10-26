"""Insight schema. Every insight must carry at least one supporting quote.

Types map onto CRM-style properties so the auto-write vs review split reads like a real
write policy. Sales methodologies (MEDDIC, BANT) extend this by adding types, not fields.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from core.config import Condition


class InsightType(StrEnum):
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    COST_FIGURE = "cost_figure"
    OPEN_RISK = "open_risk"


CRM_PROPERTY = {
    InsightType.DECISION: "decisions",
    InsightType.ACTION_ITEM: "next_steps",
    InsightType.COST_FIGURE: "budget",
    InsightType.OPEN_RISK: "risks",
}


class Quote(BaseModel):
    text: str = Field(min_length=1)  # the transcript's words, not the model's paraphrase
    speaker: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    match_score: float = Field(default=1.0, ge=0, le=1)  # how closely the model's quote matched

    @model_validator(mode="after")
    def _ordered(self) -> "Quote":
        if self.end < self.start:
            raise ValueError("quote ends before it starts")
        return self


class Insight(BaseModel):
    id: str
    meeting_id: str
    condition: Condition
    type: InsightType
    summary: str = Field(min_length=1)
    owner: str | None = None     # AMI role for action items; None means unassigned
    deadline: str | None = None  # as stated ("next meeting", "in 30 minutes")
    value: str | None = None     # the figure for cost items, e.g. "12.50 EUR"
    evidence: list[Quote] = Field(min_length=1)
    model_confidence: int | None = None  # extractor's own 0-100 rating; a risk-model baseline
    run: int = 0                 # repeat index; repeated CLEAN runs measure self-disagreement

    @model_validator(mode="after")
    def _type_fields(self) -> "Insight":
        if self.type == InsightType.COST_FIGURE and not self.value:
            raise ValueError("cost_figure insights need a value")
        if self.type != InsightType.ACTION_ITEM and (self.owner or self.deadline):
            raise ValueError("owner/deadline only apply to action_item insights")
        return self

    @property
    def crm_property(self) -> str:
        return CRM_PROPERTY[self.type]
