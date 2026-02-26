"""Pydantic models for the 4C Feature Recommender agent (both passes)."""

from pydantic import BaseModel, field_validator


class ScoreBreakdown(BaseModel):
    """Score axes for a recommendation."""

    user_value: int = 0           # 1-10
    novelty: int = 0              # 1-10
    feasibility: int = 0          # 1-10 (estimated in pass 1, actual in pass 2)
    accessibility_impact: int = 0  # 1-10 (how much this improves accessibility/UX quality)


class Recommendation(BaseModel):
    """A single feature/UX improvement recommendation."""

    id: str                    # e.g. "REC-001"
    title: str
    description: str
    rationale: str = ""
    category: str = ""         # "quick-win", "medium-term", "long-term"
    estimated_complexity: str = ""  # "low", "medium", "high"
    expected_impact: str = ""
    scores: ScoreBreakdown = ScoreBreakdown()
    rank: int = 0
    # Parity tracking — set when recommendation is driven by competitor feature gap
    parity_gap: bool = False
    competitors_with_feature: list[str] = []  # competitor names that already have this
    user_value_signal: str = ""  # "low" | "medium" | "high" from 4A research data

    @field_validator("user_value_signal", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v: object) -> object:
        return "" if v is None else v


class Pass1Output(BaseModel):
    """Output from 4C Pass 1 — initial ranking based on 4A + 4B."""

    recommendations: list[Recommendation]
    quick_wins: list[str] = []       # IDs of quick-win recommendations
    long_term: list[str] = []        # IDs of long-term recommendations
    summary: str = ""


class Pass2Output(BaseModel):
    """Output from 4C Pass 2 — re-ranked with feasibility + quality data."""

    recommendations: list[Recommendation]
    promoted: list[str] = []         # IDs that moved up in ranking
    demoted: list[str] = []          # IDs that moved down
    quick_wins: list[str] = []
    long_term: list[str] = []
    summary: str = ""
