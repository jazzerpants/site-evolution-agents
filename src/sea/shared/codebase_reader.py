"""Gitignore-aware file traversal for reading arbitrary codebases."""

from __future__ import annotations

import logging
from pathlib import Path

import pathspec

logger = logging.getLogger(__name__)

# Hard-coded exclusions that should never be read
_ALWAYS_IGNORE = {
    ".git",
    "node_modules",
    "__pycache__",
    ".next",
    ".nuxt",
    "dist",
    "build",
    ".cache",
    ".turbo",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
}

# Max file size to read (1 MB)
_MAX_FILE_SIZE = 1_024 * 1_024

# Binary extensions to skip
_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".br",
    ".mp4", ".webm", ".mp3", ".wav",
    ".pdf", ".doc", ".docx",
    ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".lock",
}


class CodebaseReader:
    """Read files from a codebase, respecting .gitignore rules."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Codebase root is not a directory: {self.root}")
        self._spec = self._load_gitignore()

    def _load_gitignore(self) -> pathspec.PathSpec | None:
        gi = self.root / ".gitignore"
        if gi.exists():
            return pathspec.PathSpec.from_lines("gitignore", gi.read_text().splitlines())
        return None

    def _is_ignored(self, rel: Path) -> bool:
        """Check if a path should be ignored."""
        # Always-ignore dirs
        for part in rel.parts:
            if part in _ALWAYS_IGNORE:
                return True
        # Gitignore spec
        if self._spec and self._spec.match_file(str(rel)):
            return True
        return False

    def _is_binary(self, path: Path) -> bool:
        return path.suffix.lower() in _BINARY_EXTENSIONS

    # ------------------------------------------------------------------
    # Public API — these map to tool calls agents can make
    # ------------------------------------------------------------------

    def list_directory(self, subpath: str = ".") -> list[str]:
        """List immediate children of a directory (non-recursive)."""
        target = (self.root / subpath).resolve()
        if not target.is_dir():
            return [f"Error: not a directory: {subpath}"]
        if not str(target).startswith(str(self.root)):
            return ["Error: path escapes codebase root"]

        entries = []
        for child in sorted(target.iterdir()):
            rel = child.relative_to(self.root)
            if self._is_ignored(rel):
                continue
            marker = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{marker}")
        return entries

    def read_file(self, subpath: str, *, max_lines: int = 500) -> str:
        """Read a single file and return its contents (capped at max_lines)."""
        target = (self.root / subpath).resolve()
        if not str(target).startswith(str(self.root)):
            return "Error: path escapes codebase root"
        if not target.is_file():
            return f"Error: not a file: {subpath}"
        if self._is_binary(target):
            return f"[binary file: {target.suffix}]"
        if target.stat().st_size > _MAX_FILE_SIZE:
            return f"[file too large: {target.stat().st_size:,} bytes]"

        try:
            text = target.read_text(errors="replace")
            lines = text.splitlines(keepends=True)
            if len(lines) > max_lines:
                remaining = len(lines) - max_lines
                return "".join(lines[:max_lines]) + f"\n[... truncated, {remaining} more lines]"
            return text
        except Exception as exc:
            return f"Error reading file: {exc}"

    def search_code(self, pattern: str, *, max_results: int = 15) -> list[dict[str, str]]:
        """Search file contents for a pattern (case-insensitive substring match).

        Returns list of {file, line_number, line} dicts.
        """
        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to literal substring
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        results: list[dict[str, str]] = []
        for path in self._walk_files():
            if self._is_binary(path):
                continue
            if path.stat().st_size > _MAX_FILE_SIZE:
                continue
            try:
                text = path.read_text(errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    rel = str(path.relative_to(self.root))
                    results.append({
                        "file": rel,
                        "line_number": str(i),
                        "line": line.rstrip()[:200],
                    })
                    if len(results) >= max_results:
                        return results
        return results

    def get_tree(self, *, max_depth: int = 3) -> str:
        """Return an indented directory tree string."""
        lines: list[str] = []
        self._tree_recurse(self.root, lines, depth=0, max_depth=max_depth)
        return "\n".join(lines)

    def read_manifest(self) -> str:
        """Read the project manifest (package.json, pyproject.toml, etc.)."""
        candidates = [
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "composer.json",
            "Gemfile",
            "pom.xml",
            "build.gradle",
        ]
        found = []
        for name in candidates:
            p = self.root / name
            if p.exists():
                found.append(f"=== {name} ===\n{p.read_text(errors='replace')}")
        return "\n\n".join(found) if found else "No manifest file found."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk_files(self) -> list[Path]:
        """Walk all non-ignored files."""
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root)
            if self._is_ignored(rel):
                continue
            files.append(path)
        return files

    def _tree_recurse(
        self, directory: Path, lines: list[str], depth: int, max_depth: int
    ) -> None:
        if depth > max_depth:
            return
        indent = "  " * depth
        for child in sorted(directory.iterdir()):
            rel = child.relative_to(self.root)
            if self._is_ignored(rel):
                continue
            if child.is_dir():
                lines.append(f"{indent}{child.name}/")
                self._tree_recurse(child, lines, depth + 1, max_depth)
            else:
                lines.append(f"{indent}{child.name}")
