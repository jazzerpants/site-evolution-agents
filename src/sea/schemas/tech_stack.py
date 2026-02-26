"""Pydantic models for the 4G Tech Stack Advisor agent output."""

import re

from pydantic import BaseModel, field_validator


def _normalize_mermaid(source: str) -> str:
    """Normalize model-generated Mermaid source to the format Mermaid.js 11 expects.

    Models sometimes output semicolon-separated single-line diagrams
    (e.g. ``graph TD; classDef keep ...; nodeA[Label]:::keep``) instead of
    the newline-separated ``flowchart TD`` format required by Mermaid 11.
    This validator converts both forms to a consistent multi-line format.

    Normalizations applied:
    - ``graph TD`` → ``flowchart TD``
    - ``graph LR`` → ``flowchart LR``
    - Semicolons used as statement separators → newlines
    """
    s = source.strip()
    # Normalise graph TD/LR to flowchart (Mermaid 11 preferred syntax)
    s = re.sub(r"^graph\s+(TD|LR|BT|RL)", r"flowchart \1", s, flags=re.IGNORECASE)
    # If already multi-line, nothing more to do
    if "\n" in s:
        return s
    # Single-line semicolon-separated: split on "; " boundaries
    # Be careful not to split inside node labels like "nodeA[A; B]"
    lines = []
    current = ""
    depth = 0  # track bracket depth to avoid splitting inside [ ]
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
            current += ch
        elif ch in ")]":
            depth -= 1
            current += ch
        elif ch == ";" and depth == 0:
            stripped = current.strip()
            if stripped:
                lines.append(stripped)
            current = ""
            # skip any whitespace after semicolon
            while i + 1 < len(s) and s[i + 1] == " ":
                i += 1
        else:
            current += ch
        i += 1
    if current.strip():
        lines.append(current.strip())
    return "\n    ".join(lines)


class ArchitectureDiagram(BaseModel):
    """A Mermaid architecture diagram for one implementation phase.

    Used to visually communicate current state and implementation impact
    to both technical and non-technical stakeholders.
    """

    title: str  # e.g. "Current Architecture", "Simple: Add Fuse.js Search"
    phase: str  # "current" | "simple" | "comprehensive"
    mermaid: str  # Mermaid diagram source (flowchart TD, multi-line)

    @field_validator("mermaid", mode="before")
    @classmethod
    def normalize_mermaid_format(cls, v: object) -> object:
        """Convert semicolon-separated or graph TD diagrams to flowchart TD newline format."""
        if isinstance(v, str):
            return _normalize_mermaid(v)
        return v
    summary: str  # Plain-English description for non-technical audiences
    # Component classifications for legend + accessibility
    components_to_keep: list[str] = []      # Existing components that work fine (green)
    components_with_issues: list[str] = []  # Existing components that are problematic (red)
    components_to_modify: list[str] = []    # Existing components that need changes (yellow)
    new_components: list[str] = []          # Net-new components required (blue)


class TechApproach(BaseModel):
    """One implementation approach (simple or comprehensive) for a feature."""

    approach_name: str  # "simple" | "comprehensive"
    description: str
    tech_stack: list[str] = []  # e.g. ["Fuse.js"] or ["Algolia", "Next.js API Routes"]
    new_dependencies: list[str] = []  # net-new packages/services required
    architecture_fit: str = ""  # "fits_as_is" | "minor_changes" | "major_changes" | "requires_migration"
    architecture_changes: list[str] = []  # specific changes needed to existing arch
    effort_estimate: str = ""  # e.g. "1-2 days", "1-2 weeks"
    pros: list[str] = []
    cons: list[str] = []


class TechStackRecommendation(BaseModel):
    """Tech stack recommendation for a single feature, with architecture diagrams."""

    feature_name: str
    parity_source: list[str] = []  # competitor names that already implement this feature
    simple_approach: TechApproach
    comprehensive_approach: TechApproach | None = None  # None if no meaningful diff
    recommended_approach: str = ""  # "simple" | "comprehensive"
    recommendation_rationale: str = ""
    current_stack_compatibility: str = ""  # summary of how well this fits the existing stack
    # Architecture diagrams: one per phase (current, simple, comprehensive)
    diagrams: list[ArchitectureDiagram] = []


class TechStackAdvisorOutput(BaseModel):
    """Full output from the 4G Tech Stack Advisor agent."""

    features: list[TechStackRecommendation]
    summary: str = ""
