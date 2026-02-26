"""Pydantic models for the 4B Code Analysis agent output."""

from pydantic import BaseModel


class TechStackItem(BaseModel):
    """A single technology in the stack."""

    name: str
    category: str  # e.g. "framework", "styling", "state-management"
    version: str = ""
    ux_pros: list[str] = []
    ux_cons: list[str] = []


class ComponentInfo(BaseModel):
    """Summary of a UI component found in the codebase."""

    name: str
    file_path: str
    description: str = ""
    has_tests: bool = False


class TechDebtItem(BaseModel):
    """A tech debt issue found in the codebase."""

    description: str
    severity: str  # "low", "medium", "high"
    location: str = ""
    suggestion: str = ""


class ArchitectureOverview(BaseModel):
    """High-level architecture summary."""

    routing_pattern: str = ""
    data_flow: str = ""
    component_tree_summary: str = ""
    mermaid_diagram: str = ""


class ExtensibilityReport(BaseModel):
    """How easy it is to add new features."""

    overall_score: str = ""  # "low", "medium", "high"
    strengths: list[str] = []
    weaknesses: list[str] = []
    notes: str = ""


class DesignSystemAnalysis(BaseModel):
    """Analysis of the interface/design system."""

    has_design_system: bool = False
    semantic_tokens: list[str] = []
    theming_support: str = ""
    animation_patterns: list[str] = []
    component_library: str = ""


class CodeAnalysisOutput(BaseModel):
    """Full output from the 4B Code Analysis agent."""

    tech_stack: list[TechStackItem]
    architecture: ArchitectureOverview
    components: list[ComponentInfo] = []
    tech_debt: list[TechDebtItem] = []
    extensibility: ExtensibilityReport = ExtensibilityReport()
    design_system: DesignSystemAnalysis = DesignSystemAnalysis()
    bundle_notes: str = ""
    summary: str = ""
