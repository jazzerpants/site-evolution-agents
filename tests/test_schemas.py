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

    def test_paren_in_label_quoted_multiline(self) -> None:
        """Labels with ( ) in multi-line diagrams are wrapped in quotes."""
        src = (
            "flowchart TD\n"
            "    tailwindConfig[Tailwind Config (presumed)]:::keep\n"
            "    appRoot --> tailwindConfig"
        )
        result = _normalize_mermaid(src)
        assert '["Tailwind Config (presumed)"]' in result

    def test_paren_in_label_quoted_singleline(self) -> None:
        """Labels with ( ) in single-line semicolon diagrams are wrapped in quotes."""
        src = "flowchart TD; nodeA[Config (presumed)]:::keep; nodeB[Other]"
        result = _normalize_mermaid(src)
        assert '["Config (presumed)"]' in result

    def test_cylinder_shape_not_quoted(self) -> None:
        """Cylinder shapes [(text)] must NOT be wrapped in quotes."""
        src = (
            "flowchart TD\n"
            "    A[App Root] --> B[(auth)]:::keep\n"
            "    A --> C[(home)]:::keep"
        )
        result = _normalize_mermaid(src)
        # Cylinders must be preserved as-is
        assert "[(auth)]" in result
        assert "[(home)]" in result
        # No spurious quoting
        assert '["(auth)"]' not in result

    def test_trailing_semicolon_on_declaration_stripped(self) -> None:
        """flowchart TD; trailing semicolons are removed from the declaration line."""
        src = "flowchart TD;\n    A[Node]:::keep"
        result = _normalize_mermaid(src)
        assert result.startswith("flowchart TD\n")
        assert ";" not in result.splitlines()[0]

    def test_already_quoted_label_unchanged(self) -> None:
        """Labels already in [\"...\"] form are not double-quoted."""
        src = 'flowchart TD\n    A["Already (quoted)"] --> B'
        result = _normalize_mermaid(src)
        assert result.count('"') == 2  # exactly the original two quotes

    def test_semicolons_inside_quoted_labels_not_split(self) -> None:
        """Semicolons inside double-quoted labels are preserved."""
        # Only 1 separator semicolon (after flowchart TD), so 2 output lines.
        # The semicolons inside ["..."] must NOT be treated as separators.
        src = 'flowchart TD; A["Label; with; semicolons"] --> B[Other]'
        result = _normalize_mermaid(src)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}: {lines}"
        assert any('Label; with; semicolons' in l for l in lines)

    def test_multiple_quoted_nodes_split_correctly(self) -> None:
        """Separator semicolons between nodes are split; inner ones are preserved."""
        src = 'flowchart TD; A["Entry; A"] --> B; B["Exit; B"]'
        result = _normalize_mermaid(src)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        # 3 lines: header, edge A→B, standalone B label
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}: {lines}"
        assert any('Entry; A' in l for l in lines)
        assert any('Exit; B' in l for l in lines)

    def test_semicolons_inside_curly_braces_not_split(self) -> None:
        """Semicolons inside curly-brace nodes {text} are preserved."""
        # Only 1 separator semicolon (after flowchart TD), so 2 output lines.
        src = "flowchart TD; A{Choice; A or B} --> B[Done]"
        result = _normalize_mermaid(src)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}: {lines}"
        assert any("Choice; A or B" in l for l in lines)

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
