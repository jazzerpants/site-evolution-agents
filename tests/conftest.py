"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sea.shared.claude_client import ClaudeClient

# Root of the test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Write a minimal valid config YAML and return its path."""
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        """\
target_path: "{target}"
priorities:
  - "Test priority"
output_directory: "{out}"
""".format(target=str(tmp_path), out=str(tmp_path / "output"))
    )
    return cfg


@pytest.fixture
def mock_claude_client() -> ClaudeClient:
    """Return a ClaudeClient with a mocked Anthropic SDK underneath."""
    client = ClaudeClient.__new__(ClaudeClient)
    client._client = AsyncMock()
    return client
