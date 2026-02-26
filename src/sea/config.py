"""YAML config loader — reads analysis-config.yml into AnalysisConfig."""

from pathlib import Path

import yaml

from sea.schemas.config import AnalysisConfig


def load_config(path: str | Path) -> AnalysisConfig:
    """Load and validate an analysis config file.

    Raises ``FileNotFoundError`` if the path doesn't exist and
    ``pydantic.ValidationError`` if the YAML content is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

    # YAML loads lists with only commented-out items as None; normalize to empty list.
    # Also strip empty-string or None items from actual lists.
    for key in ("competitor_urls", "known_issues", "design_assets"):
        if key in raw:
            if raw[key] is None:
                raw[key] = []
            elif isinstance(raw[key], list):
                raw[key] = [item for item in raw[key] if item]

    return AnalysisConfig(**raw)
