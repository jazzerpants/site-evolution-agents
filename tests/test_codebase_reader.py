"""Tests for CodebaseReader — file traversal, search, and gitignore support."""

from pathlib import Path

import pytest

from sea.shared.codebase_reader import CodebaseReader


@pytest.fixture
def sample_codebase(tmp_path: Path) -> Path:
    """Create a small fake codebase for testing."""
    # Create files
    (tmp_path / "package.json").write_text('{"name": "test-app"}')
    (tmp_path / "README.md").write_text("# Test App")

    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text("export const hello = 'world';")
    (src / "utils.ts").write_text("export function add(a: number, b: number) { return a + b; }")

    components = src / "components"
    components.mkdir()
    (components / "Button.tsx").write_text("<button>{children}</button>")

    # Create a node_modules dir that should be ignored
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "lodash.js").write_text("module.exports = {}")

    # Create a .gitignore
    (tmp_path / ".gitignore").write_text("*.log\n.env\n")

    # Create files that should be ignored by .gitignore
    (tmp_path / "debug.log").write_text("some log")
    (tmp_path / ".env").write_text("SECRET=abc")

    return tmp_path


class TestCodebaseReader:

    def test_init_requires_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "not-a-dir.txt"
        f.write_text("hi")
        with pytest.raises(ValueError, match="not a directory"):
            CodebaseReader(f)

    def test_list_directory_root(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        entries = reader.list_directory()
        assert "package.json" in entries
        assert "README.md" in entries
        assert "src/" in entries
        # node_modules should be excluded
        assert "node_modules/" not in entries
        # .gitignore-excluded files
        assert "debug.log" not in entries
        assert ".env" not in entries

    def test_list_directory_subdir(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        entries = reader.list_directory("src")
        assert "index.ts" in entries
        assert "components/" in entries

    def test_read_file(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        content = reader.read_file("src/index.ts")
        assert "hello" in content

    def test_read_file_not_found(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        result = reader.read_file("nonexistent.ts")
        assert "Error" in result

    def test_read_file_prevents_path_escape(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        result = reader.read_file("../../etc/passwd")
        assert "Error" in result

    def test_search_code(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        results = reader.search_code("export")
        assert len(results) >= 2
        files = [r["file"] for r in results]
        assert any("index.ts" in f for f in files)

    def test_search_code_regex(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        results = reader.search_code(r"function\s+\w+")
        assert len(results) >= 1

    def test_get_tree(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        tree = reader.get_tree()
        assert "src/" in tree
        assert "node_modules/" not in tree

    def test_read_manifest(self, sample_codebase: Path) -> None:
        reader = CodebaseReader(sample_codebase)
        manifest = reader.read_manifest()
        assert "package.json" in manifest
        assert "test-app" in manifest
