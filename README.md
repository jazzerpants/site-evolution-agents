# Site Evolution Agents

Multi-agent system that analyzes websites and codebases to produce prioritized evolution recommendations. Seven specialized AI agents evaluate your site's design, code, performance, and competitive landscape, then synthesize actionable improvement recommendations.

## Pipeline Architecture

```
Pass 1:  4A (Comparative Research) + 4B (Code Analysis)    [parallel]
           |
         4C Pass 1 (Feature Ranking)
           |
Pass 2:  4D (Tech Feasibility) then 4E (Quality Audit)     [sequential]
           |
         4C Pass 2 (Re-ranking with feasibility + quality data)
           |
         4F (UX Design Audit)
           |
         Synthesis -> Markdown report + HTML dashboard

On-demand:
         4G (Tech Stack Advisor) — evaluate specific features independently
```

### Agents

| Agent | Role | Description |
|-------|------|-------------|
| **4A** | Comparative Research | Browses competitor sites, captures screenshots, identifies feature gaps and UX patterns |
| **4B** | Code Analysis | Analyzes the local codebase for tech stack, architecture, design system, and tech debt |
| **4C** | Feature Recommender | Synthesizes research + code analysis into ranked feature recommendations (two passes) |
| **4D** | Tech Feasibility | Assesses implementation cost, risk, and dependencies for each recommendation |
| **4E** | Quality Audit | Runs accessibility (axe-core) and performance (Core Web Vitals) audits |
| **4F** | UX Design Audit | Visually evaluates site screenshots for layout, typography, color, and navigation quality |
| **4G** | Tech Stack Advisor | Produces simple vs. comprehensive implementation approaches with Mermaid architecture diagrams |

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- `OPENAI_API_KEY` environment variable (or `.env` file in project root)

## Setup

```bash
# Install dependencies
uv sync

# Install Playwright browsers (needed for 4A and 4E)
uv run playwright install chromium

# Copy and edit configuration
cp config/analysis-config.example.yml config/analysis-config.yml
```

## Usage

```bash
# Run the full analysis pipeline
sea analyze --config config/analysis-config.yml

# Dry-run with mock data (no API calls)
sea analyze --config config/analysis-config.yml --dry-run

# Verbose logging
sea analyze --config config/analysis-config.yml --verbose

# Validate config without running
sea validate --config config/analysis-config.yml

# Evaluate specific features (simple vs. comprehensive tech stack recommendations)
sea feature --name "site search" --config config/analysis-config.yml

# Evaluate multiple features at once
sea feature --name "site search" --name "dark mode" --config config/analysis-config.yml

# Evaluate features AND update the dashboard from a previous full run
sea feature --name "site search" --config config/analysis-config.yml --patch-report ./output

# Re-render the Markdown report and HTML dashboard from a saved report.json
# (useful after template changes without re-running the full pipeline)
sea render --output ./output
```

### Feature Evaluation (`sea feature`)

The `sea feature` command runs agents 4B (Code Analysis) and 4G (Tech Stack Advisor) without the full pipeline. For each named feature it produces:

- A **simple approach** (minimal dependencies, fits existing stack)
- A **comprehensive approach** (best-in-class, may require migration)
- **Mermaid architecture diagrams** showing current state and per-approach impact
- Effort estimates, pros/cons, and a recommended approach

Results are written to `{output_directory}/feature-evaluation.json`.

Use `--patch-report <dir>` to merge the 4G results into a prior `report.json` and re-render both the Markdown report and HTML dashboard in place.

## Configuration

Edit `config/analysis-config.yml`. At minimum you need one of `target_path` or `target_url` and at least one priority:

```yaml
# At least one required
target_path: "/path/to/your/codebase"
target_url: "https://your-site.com"

# At least one required
priorities:
  - "improve user experience"
  - "increase performance"

# Optional
site_name: "My Site"
competitor_urls:
  - "https://competitor1.com"
  - "https://competitor2.com"
site_depth: 1          # 0=homepage only, 1=top-level pages, 2=two clicks deep
output_directory: "./output"
```

## Output

The pipeline generates reports in the output directory:

| File | Description |
|------|-------------|
| `evolution-report.md` | Structured Markdown report with all findings |
| `evolution-dashboard.html` | Self-contained HTML dashboard with collapsible sections, score visualizations, screenshots, and Mermaid architecture diagrams |
| `report.json` | Full pipeline state — re-render anytime with `sea render` |
| `feature-evaluation.json` | Output from `sea feature` runs |
| `screenshots/` | Saved JPEG screenshots referenced by the dashboard |

## Development

```bash
# Run all tests
uv run pytest tests/

# Run a specific test file
uv run pytest tests/test_base_agent.py

# Run a specific test
uv run pytest tests/test_agents/test_quality_audit.py::TestQualityAuditAgent::test_name
```

## Project Structure

```
src/sea/
  agents/
    comparative_research/   # 4A — browser-based competitor research
    code_analysis/          # 4B — codebase analysis
    feature_recommender/    # 4C — recommendation synthesis
    tech_feasibility/       # 4D — implementation assessment
    quality_audit/          # 4E — accessibility + performance
    ux_design/              # 4F — visual design evaluation
    tech_stack_advisor/     # 4G — simple vs. comprehensive tech approaches + architecture diagrams
    orchestrator/           # Pipeline coordinator
    base.py                 # BaseAgent ABC
  schemas/                  # Pydantic models for all agent outputs
    tech_stack.py           # TechStackAdvisorOutput + Mermaid normalization
  shared/
    claude_client.py        # OpenAI API wrapper + dry-run mock
    browser.py              # Playwright browser manager
    codebase_reader.py      # Gitignore-aware file reader
    progress.py             # Rich TUI progress display
  output/
    markdown.py             # Markdown report generator
    dashboard.py            # HTML dashboard generator (uses markdown-it-py)
    templates/              # Jinja2 templates
  cli.py                    # Typer CLI entry point
```
