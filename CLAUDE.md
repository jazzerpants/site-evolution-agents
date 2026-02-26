# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Site Evolution Agents (`sea`) is a multi-agent system that analyzes websites and codebases to produce prioritized evolution recommendations. It uses GPT-4o via the OpenAI API (despite `claude_client.py` naming — this is historical) with an agentic tool-use loop.

## Commands

```bash
# Install dependencies
uv sync

# Install Playwright browsers (needed for 4A and 4E)
uv run playwright install chromium

# Run the full pipeline
sea analyze --config config/analysis-config.yml

# Dry-run (mock data, no API calls)
sea analyze --config config/analysis-config.yml --dry-run

# Validate config only
sea validate --config config/analysis-config.yml

# Evaluate specific features (runs 4B + 4G, no full pipeline)
sea feature --name "site search" --config config/analysis-config.yml

# Evaluate features AND patch an existing report/dashboard
sea feature --name "site search" --config config/analysis-config.yml --patch-report ./output

# Re-render reports from a saved report.json (no API calls)
sea render --output ./output

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_base_agent.py

# Run a specific test
uv run pytest tests/test_agents/test_comparative_research.py::TestPageBudget::test_budget_matches_constant
```

## Environment

- Python 3.12+, managed with `uv`
- Requires `OPENAI_API_KEY` env var (or `.env` file in project root)
- Playwright Chromium for browser-based agents

## Architecture

### Two-Pass Pipeline

```
Pass 1:  4A (Comparative Research) + 4B (Code Analysis)  [parallel]
           ↓
         4C Pass 1 (Feature Ranking)
           ↓
Pass 2:  4D (Tech Feasibility) then 4E (Quality Audit)   [sequential — TPM limits]
           ↓
         4C Pass 2 (Re-ranking with feasibility/quality data)
           ↓
         Synthesis → Markdown report + HTML dashboard

On-demand (sea feature):
         4B (Code Analysis) → 4G (Tech Stack Advisor)
```

Orchestrated by `src/sea/agents/orchestrator/agent.py`. Agents 4D and 4E run sequentially (not parallel) to avoid OpenAI TPM rate limits.

`sea feature` runs a focused 4B+4G sub-pipeline. Results go to `feature-evaluation.json`. Use `--patch-report <dir>` to merge into a prior `report.json` and re-render the dashboard.

### Agent Structure

Each agent follows the `BaseAgent` ABC (`src/sea/agents/base.py`):

| Method | Purpose |
|--------|---------|
| `name` | Human-readable name for progress display |
| `get_system_prompt()` | System prompt string |
| `get_tools()` | Tool definitions (Claude format — auto-converted to OpenAI format) |
| `get_tool_handler()` | Async `(name, input) -> str \| list[str]` callable |
| `parse_output(raw)` | Parse final text into Pydantic model |

`BaseAgent.run()` handles the agent loop + automatic JSON retry via `_parse_with_retry()`. Exception: 4C (FeatureRecommenderAgent) uses `simple_completion()` with no tools.

### Agents

| Agent | Role | Tools | Browser | Codebase |
|-------|------|-------|---------|----------|
| 4A | Comparative Research | browse_page, discover_links, screenshot, extract_css, ask_user | Yes | No |
| 4B | Code Analysis | list_dir, read_file, search_code, get_tree, read_manifest | No | Yes |
| 4C | Feature Recommender | None (simple_completion) | No | No |
| 4D | Tech Feasibility | read_file, search_code | No | Yes |
| 4E | Quality Audit | run_axe, measure_vitals, screenshot, read_file, search_code | Yes | Optional |
| 4F | UX Design Audit | screenshot | Yes | No |
| 4G | Tech Stack Advisor | read_file, search_code | No | Yes |

4G processes one feature per API call to stay within `MAX_TOKENS` output limits — batching multiple features causes JSON truncation. `run_evaluation()` loops serially.

### Agent Directory Convention

Each agent lives in `src/sea/agents/<name>/` with:
- `agent.py` — agent class
- `prompts.py` — system prompt constant
- `tools.py` — tool definitions + `make_tool_handler()` factory

### Shared Layer

- **`claude_client.py`** — `ClaudeClient` wraps AsyncOpenAI. `run_agent_loop()` does the tool-use loop. `DryRunClient` returns canned JSON for testing. Tool definitions use Claude format (`input_schema`) and are auto-converted to OpenAI format (`parameters`).
- **`browser.py`** — `BrowserManager` (async context manager) wraps Playwright. `take_screenshot()` returns `list[str]` (base64 JPEG tiles, one per viewport-height). `captured_screenshots` accumulates all shots for dashboard.
- **`codebase_reader.py`** — Gitignore-aware traversal with binary detection, 1MB file limit, 500 line read limit.
- **`progress.py`** — Rich-based TUI. `update_agent()` for spinner text (transient), `log_event()` for persistent CLI messages.

### Schemas

All in `src/sea/schemas/`. Every agent output is a Pydantic model. `PipelineState` tracks intermediate results. `FinalReport` is the assembled output passed to report generators.

### Output

- `src/sea/output/markdown.py` — Markdown report
- `src/sea/output/dashboard.py` — HTML dashboard (Jinja2 template at `src/sea/output/templates/dashboard.html`); uses `markdown-it-py` for Markdown→HTML conversion
- Screenshots saved to `{output_dir}/screenshots/` as JPEG files; dashboard references them by relative path
- `report.json` saved after every full run; `sea render --output <dir>` re-renders both files without API calls

### Key Patterns

**Tool handler return types:** `str` for text results, `list[str]` for screenshot tiles. When `claude_client.py` receives a list, it sends a text summary as the tool result + a follow-up user message with `image_url` content blocks (`detail: "low"`, 85 tokens/tile).

**Page budgets (4A):** `browse_page` and `extract_css` count against a depth-based page budget. Screenshots have a separate `MAX_SCREENSHOTS` cap and don't consume page budget.

**Callbacks:** Two patterns flow through the pipeline:
- `on_progress(msg)` — transient spinner updates
- `on_event(msg)` — persistent Rich-formatted log lines

**Config:** YAML file loaded by `src/sea/config.py` into `AnalysisConfig` Pydantic model. Requires at least one of `target_path`/`target_url` and at least one priority.

**Mermaid normalization:** Models sometimes emit `graph TD; node1 --> node2` (semicolon-separated, single-line). `_normalize_mermaid()` in `src/sea/schemas/tech_stack.py` converts this to `flowchart TD` multi-line format via a `field_validator` on `ArchitectureDiagram.mermaid`. Always use this validator when adding new diagram fields.
