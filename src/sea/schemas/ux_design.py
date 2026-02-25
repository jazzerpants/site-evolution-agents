"""Pydantic models for the 4F UX Design Audit agent output."""

from pydantic import BaseModel


class LayoutAssessment(BaseModel):
    """Assessment of the site's layout and visual hierarchy."""

    visual_hierarchy: str = ""
    whitespace_usage: str = ""
    grid_consistency: str = ""
    responsive_notes: str = ""


class TypographyAssessment(BaseModel):
    """Assessment of typography choices and usage."""

    readability: str = ""
    hierarchy: str = ""
    consistency: str = ""


class ColorAssessment(BaseModel):
    """Assessment of the site's color system."""

    palette_coherence: str = ""
    contrast_notes: str = ""
    brand_consistency: str = ""
    dark_mode_notes: str = ""


class NavigationAssessment(BaseModel):
    """Assessment of navigation and information architecture."""

    clarity: str = ""
    information_architecture: str = ""
    mobile_notes: str = ""


class UXDesignIssue(BaseModel):
    """A single UX/design issue found during the audit."""

    area: str = ""  # "layout", "typography", "color", "navigation", "interaction"
    description: str
    severity: str = ""  # "critical", "major", "minor", "suggestion"
    recommendation: str = ""
    competitors_doing_better: list[str] = []


class UXDesignOutput(BaseModel):
    """Full output from the 4F UX Design Audit agent."""

    layout: LayoutAssessment = LayoutAssessment()
    typography: TypographyAssessment = TypographyAssessment()
    color: ColorAssessment = ColorAssessment()
    navigation: NavigationAssessment = NavigationAssessment()
    issues: list[UXDesignIssue] = []
    strengths: list[str] = []
    overall_impression: str = ""
    summary: str = ""
