"""Pipeline state and final report models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.schemas.config import AnalysisConfig
from sea.schemas.feasibility import FeasibilityOutput
from sea.schemas.quality import QualityAuditOutput
from sea.schemas.recommendations import Pass1Output, Pass2Output
from sea.schemas.research import ComparativeResearchOutput
from sea.schemas.ux_design import UXDesignOutput


class ScreenshotEntry(BaseModel):
    """A set of viewport-height screenshot tiles for a single URL."""

    url: str
    tiles: list[str]  # base64 JPEG strings (sent to model)
    full_page: str = ""  # single full-page JPEG base64 (dashboard only)


class PipelineState(BaseModel):
    """Tracks the state of data flowing through the pipeline."""

    config: AnalysisConfig
    research: ComparativeResearchOutput | None = None
    code_analysis: CodeAnalysisOutput | None = None
    pass1: Pass1Output | None = None
    feasibility: FeasibilityOutput | None = None
    quality_audit: QualityAuditOutput | None = None
    pass2: Pass2Output | None = None
    ux_design: UXDesignOutput | None = None
    screenshots: list[ScreenshotEntry] = []


class FinalReport(BaseModel):
    """The complete output of the pipeline."""

    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    config: AnalysisConfig
    research: ComparativeResearchOutput | None = None
    code_analysis: CodeAnalysisOutput | None = None
    recommendations: Pass2Output | Pass1Output | None = None
    feasibility: FeasibilityOutput | None = None
    quality_audit: QualityAuditOutput | None = None
    ux_design: UXDesignOutput | None = None
    screenshots: list[ScreenshotEntry] = []
