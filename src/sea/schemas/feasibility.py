"""Pydantic models for the 4D Technology Feasibility agent output."""

from pydantic import BaseModel, field_validator


class ProCon(BaseModel):
    """A single pro or con for a proposed change."""

    point: str
    weight: str = ""  # "minor", "moderate", "major"


class FeasibilityAssessment(BaseModel):
    """Feasibility assessment for a single recommendation."""

    recommendation_id: str
    rating: str = ""  # "easy", "moderate", "hard", "requires_migration"
    cost_estimate: str = ""  # "small", "medium", "large"
    developer_days: str = ""  # e.g. "1-2 days", "1-2 weeks"

    @field_validator("developer_days", mode="before")
    @classmethod
    def _coerce_developer_days(cls, v: object) -> str:
        """The model sometimes returns an int instead of a string."""
        return str(v) if not isinstance(v, str) else v

    new_dependencies: list[str] = []
    migration_path: str = ""
    risk: str = ""  # "low", "medium", "high"
    pros: list[ProCon] = []
    cons: list[ProCon] = []
    notes: str = ""


class FollowUpQA(BaseModel):
    """A single ad-hoc follow-up question and answer."""

    question: str
    answer: str
    asked_at: str = ""  # ISO timestamp


class FeasibilityOutput(BaseModel):
    """Full output from the 4D Technology Feasibility agent."""

    assessments: list[FeasibilityAssessment]
    summary: str = ""
    follow_up_qa: list[FollowUpQA] = []
