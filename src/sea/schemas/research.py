"""Pydantic models for the 4A Comparative Research agent output."""

from pydantic import BaseModel


class CompetitorProfile(BaseModel):
    """Profile of a competitor/reference site."""

    name: str
    url: str
    relevance: str = ""  # why this site is a good comparison
    strengths: list[str] = []
    weaknesses: list[str] = []


class FeatureMatrixEntry(BaseModel):
    """One row in the competitive feature matrix."""

    feature: str
    current_site: str = ""  # "yes", "no", "partial"
    competitors: dict[str, str] = {}  # competitor_name -> "yes"/"no"/"partial"


class UXPattern(BaseModel):
    """A UX pattern observed in competitor analysis."""

    name: str
    description: str
    seen_in: list[str] = []  # which competitors use it
    relevance: str = ""  # why it matters for the target site


class GapItem(BaseModel):
    """Something the current site is missing."""

    description: str
    severity: str = ""  # "low", "medium", "high"
    user_value: str = ""  # "low", "medium", "high" — how much users rely on this feature
    competitor_prevalence: int = 0  # how many competitors have it (e.g. 4 out of 4)
    competitors_with_feature: list[str] = []


class DesignSystemReference(BaseModel):
    """A design system or pattern library discovered."""

    name: str
    url: str = ""
    notes: str = ""


class ComparativeResearchOutput(BaseModel):
    """Full output from the 4A Comparative Research agent."""

    competitors: list[CompetitorProfile]
    feature_matrix: list[FeatureMatrixEntry] = []
    ux_patterns: list[UXPattern] = []
    gaps: list[GapItem] = []
    trends: list[str] = []
    design_systems: list[DesignSystemReference] = []
    summary: str = ""
