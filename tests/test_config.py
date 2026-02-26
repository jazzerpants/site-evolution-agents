"""Tests for config loading and validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from sea.config import load_config
from sea.schemas.config import AnalysisConfig, Constraints


class TestAnalysisConfig:
    """Test the AnalysisConfig Pydantic model directly."""

    def test_valid_minimal_with_path(self, tmp_path: Path) -> None:
        cfg = AnalysisConfig(target_path=str(tmp_path), priorities=["perf"])
        assert cfg.target_path == str(tmp_path)
        assert cfg.priorities == ["perf"]

    def test_valid_minimal_with_url(self) -> None:
        cfg = AnalysisConfig(target_url="https://example.com", priorities=["ux"])
        assert cfg.target_url == "https://example.com"

    def test_requires_at_least_one_target(self) -> None:
        with pytest.raises(ValidationError, match="target_path.*target_url"):
            AnalysisConfig(priorities=["ux"])

    def test_requires_at_least_one_priority(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="priority"):
            AnalysisConfig(target_path=str(tmp_path), priorities=[])

    def test_target_path_must_exist(self) -> None:
        with pytest.raises(ValidationError, match="does not exist"):
            AnalysisConfig(target_path="/nonexistent/path", priorities=["ux"])

    def test_defaults(self, tmp_path: Path) -> None:
        cfg = AnalysisConfig(target_path=str(tmp_path), priorities=["a"])
        assert cfg.competitor_urls == []
        assert cfg.known_issues == []
        assert cfg.output_directory == "./output"
        assert cfg.constraints == Constraints()

    def test_full_config(self, tmp_path: Path) -> None:
        cfg = AnalysisConfig(
            target_path=str(tmp_path),
            target_url="https://example.com",
            priorities=["perf", "ux"],
            site_name="My Site",
            site_description="A test site",
            competitor_urls=["https://rival.com"],
            known_issues=["slow load"],
            constraints=Constraints(must_keep=["Next.js"], budget="2 weeks"),
        )
        assert cfg.site_name == "My Site"
        assert cfg.constraints.must_keep == ["Next.js"]


class TestLoadConfig:
    """Test YAML file loading."""

    def test_load_valid_file(self, tmp_config: Path) -> None:
        cfg = load_config(tmp_config)
        assert cfg.priorities == ["Test priority"]

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yml"
        bad.write_text("just a string")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad)

    def test_null_lists_become_empty(self, tmp_path: Path) -> None:
        """YAML files with commented-out list items load as None."""
        cfg_file = tmp_path / "config.yml"
        cfg_file.write_text(
            f"""\
target_path: "{tmp_path}"
priorities:
  - "test"
competitor_urls:
  # - "https://example.com"
known_issues:
design_assets:
"""
        )
        cfg = load_config(cfg_file)
        assert cfg.competitor_urls == []
        assert cfg.known_issues == []
        assert cfg.design_assets == []

