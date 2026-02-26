"""Tests for Pydantic schema models — round-trip serialization."""

import json

from sea.schemas.config import AnalysisConfig, Constraints
from sea.schemas.tech_stack import ArchitectureDiagram, _normalize_mermaid


class TestNormalizeMermaid:
    """_normalize_mermaid converts model output to Mermaid 11-compatible format."""

    def test_multiline_unchanged(self) -> None:
        """Already multi-line flowchart TD is returned as-is."""
        src = "flowchart TD\n    nodeA[Label]:::keep\n    nodeB[Other]:::new"
        assert _normalize_mermaid(src) == src

    def test_graph_td_converted_to_flowchart(self) -> None:
        """graph TD is upgraded to flowchart TD."""
        src = "graph TD\n    A --> B"
        result = _normalize_mermaid(src)
        assert result.startswith("flowchart TD")
        assert "graph TD" not in result

    def test_graph_lr_converted(self) -> None:
        src = "graph LR\n    A --> B"
        assert _normalize_mermaid(src).startswith("flowchart LR")

    def test_single_line_semicolons_split_to_newlines(self) -> None:
        """Semicolon-separated single-line format is split into multi-line."""
        src = "flowchart TD; classDef keep fill:#4ade80; nodeA[Label]:::keep"
        result = _normalize_mermaid(src)
        assert "\n" in result
        assert "classDef keep" in result
        assert "nodeA[Label]:::keep" in result

    def test_semicolons_inside_brackets_not_split(self) -> None:
        """Semicolons inside node labels [...] are preserved."""
        src = "flowchart TD; nodeA[Hello; World]:::keep; nodeB[Other]:::new"
        result = _normalize_mermaid(src)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        # Should be 3 lines: header + 2 nodes
        assert len(lines) == 3
        assert any("Hello; World" in l for l in lines)

    def test_graph_td_single_line_fully_normalized(self) -> None:
        """graph TD with semicolons gets both graph→flowchart and ; → newline fixes."""
        src = "graph TD; classDef keep fill:#4ade80,stroke:#22c55e,color:#0f172a; nodeA[Nav]:::keep"
        result = _normalize_mermaid(src)
        assert result.startswith("flowchart TD")
        assert "\n" in result
        assert "classDef keep" in result

    def test_validator_applied_on_model_parse(self) -> None:
        """ArchitectureDiagram.mermaid is normalized at parse time."""
        diag = ArchitectureDiagram(
            title="Test",
            phase="current",
            mermaid="graph TD; nodeA[A]:::keep; nodeB[B]:::issue",
            summary="test summary",
        )
        assert diag.mermaid.startswith("flowchart TD")
        assert "\n" in diag.mermaid


class TestSchemaRoundTrip:
    """Verify models can serialize to JSON and back."""

    def test_config_round_trip(self, tmp_path) -> None:
        original = AnalysisConfig(
            target_path=str(tmp_path),
            priorities=["perf", "ux"],
            site_name="Test",
            constraints=Constraints(must_keep=["React"], budget="1 week"),
        )
        as_json = original.model_dump_json()
        restored = AnalysisConfig.model_validate_json(as_json)
        assert restored.site_name == "Test"
        assert restored.constraints.must_keep == ["React"]
        assert restored.priorities == ["perf", "ux"]

    def test_config_to_dict(self, tmp_path) -> None:
        cfg = AnalysisConfig(target_path=str(tmp_path), priorities=["a"])
        d = cfg.model_dump()
        assert isinstance(d, dict)
        assert d["priorities"] == ["a"]
