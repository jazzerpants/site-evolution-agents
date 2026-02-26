"""Configuration schema — validates analysis-config.yml."""

from pathlib import Path

from pydantic import BaseModel, model_validator


class Constraints(BaseModel):
    """Technology and process constraints for the analysis."""

    must_keep: list[str] = []
    must_avoid: list[str] = []
    budget: str = ""


class AnalysisConfig(BaseModel):
    """Top-level configuration loaded from analysis-config.yml.

    At least one of ``target_path`` or ``target_url`` must be provided,
    and at least one priority is required.
    """

    # Required — at least one
    target_path: str = ""
    target_url: str = ""

    # Priorities — at least one required
    priorities: list[str]

    # Optional metadata
    site_name: str = ""
    site_description: str = ""

    # Optional lists
    competitor_urls: list[str] = []
    known_issues: list[str] = []
    user_feedback: str = ""
    design_assets: list[str] = []

    # Specific features to evaluate with 4G Tech Stack Advisor.
    # e.g. ["search", "authentication", "dark mode"]
    # If empty, 4G will evaluate features surfaced as parity gaps by 4A/4C.
    features: list[str] = []

    # Analysis tuning
    site_depth: int = 1  # 0=homepage only, 1=top-level pages, 2=two clicks deep

    # Output
    output_directory: str = "./output"

    # Constraints
    constraints: Constraints = Constraints()

    @model_validator(mode="after")
    def check_has_target(self) -> "AnalysisConfig":
        if not self.target_path and not self.target_url:
            raise ValueError(
                "At least one of 'target_path' or 'target_url' must be provided"
            )
        return self

    @model_validator(mode="after")
    def check_has_priorities(self) -> "AnalysisConfig":
        if not self.priorities:
            raise ValueError("At least one priority is required")
        return self

    @model_validator(mode="after")
    def check_target_path_exists(self) -> "AnalysisConfig":
        if self.target_path:
            p = Path(self.target_path)
            if not p.exists():
                raise ValueError(f"target_path does not exist: {self.target_path}")
        return self
