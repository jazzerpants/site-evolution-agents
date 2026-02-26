"""Pydantic models for the 4E Quality Audit agent output."""

from pydantic import BaseModel, field_validator


class AccessibilityIssue(BaseModel):
    """A single accessibility finding."""

    description: str
    severity: str = ""  # "critical", "serious", "moderate", "minor"
    wcag_criterion: str = ""  # e.g. "1.1.1"
    element: str = ""
    suggestion: str = ""


class PerformanceMetric(BaseModel):
    """A single performance measurement."""

    name: str  # e.g. "LCP", "FCP", "CLS"
    value: str = ""
    rating: str = ""  # "good", "needs-improvement", "poor"
    notes: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value_to_str(cls, v: object) -> str:
        return str(v) if not isinstance(v, str) else v


class AccessibilityReport(BaseModel):
    """Accessibility audit results."""

    wcag_level: str = ""  # "A", "AA", "AAA"
    issues: list[AccessibilityIssue] = []
    keyboard_navigation: str = ""
    screen_reader_notes: str = ""
    aria_usage: str = ""


class PerformanceReport(BaseModel):
    """Performance audit results."""

    metrics: list[PerformanceMetric] = []
    bundle_analysis: str = ""
    image_optimization: str = ""
    caching_strategy: str = ""
    critical_rendering_path: str = ""


class QualityIssue(BaseModel):
    """A prioritized quality issue."""

    description: str
    category: str = ""  # "accessibility" or "performance"
    impact: str = ""  # "low", "medium", "high"
    effort_to_fix: str = ""


class QualityAuditOutput(BaseModel):
    """Full output from the 4E Quality Audit agent."""

    accessibility: AccessibilityReport = AccessibilityReport()
    performance: PerformanceReport = PerformanceReport()
    priority_issues: list[QualityIssue] = []
    summary: str = ""
