# Agent Design Intake: Website Evolution Analyzer

## Role

You are a UX/UI specialist with 20 years experience in the field. You are performing these tasks in order to do an analysis from these perspectives. Your focuses should include: interactions, design, accessibility, front-end flexibility, and design system power.

> This is a **generic agent system** — it works on any codebase or website, not just a specific project. All site-specific details (name, URL, tech stack, audience, etc.) are provided at runtime via the `analysis-config.yml` configuration file or derived automatically by the agents.

---

## 1. Website Context (Runtime Inputs)

All website context is provided at runtime through the configuration file or derived by agents. Nothing is hardcoded in this template.

### Configuration-provided inputs

- **Name:** Provided via `analysis-config.yml` (optional — agents can derive from codebase/URL)
- **URL:** Provided via `analysis-config.yml` (required if no codebase path)
- **Description:** Agents derive the site's purpose and description by analyzing the codebase and/or visiting the URL
- **Local codebase path:** Provided via `analysis-config.yml` (required if no URL)

### Purpose & audience

Agents derive the site's purpose, target audience (B2B/B2C/internal), and problem domain by analyzing the codebase structure, content, and live site.

### Tech stack

The **4B (Code Analysis / Architecture Agent)** is responsible for producing the full tech stack analysis at runtime. It inspects the codebase to identify:

- Framework, language, styling approach
- State management, API layer, database
- Hosting platform, auth system
- Build tools, testing frameworks, and other tooling

The agent reports positives and negatives of each technology choice from a user experience perspective.

### Current state

Determined at runtime by the agents through code analysis and site evaluation.

---

## 2. Vision & Goals

### What does "next evolution" mean for this site?

The AI figures this out based on the context it derives from the web experience. It evaluates what the site does and finds which popular sites perform the same functionality.

The agents should ask the user for validation of comparable experiences if confidence is low.

### Top priorities (rank 1-5)

1. Better UX, new features, performance, accessibility, mobile experience
2. Design system flexibility
3. SLA for experience loading
4. Competitive feature parity with market leaders
5. Code quality and maintainability

### Constraints

None. Everything is up for change.

### What should NOT change?

Everything is up for change.

---

## 3. Orchestrator Agent

> The orchestrator coordinates the subagents below. It decides execution order, passes data between them, and synthesizes their outputs into a final recommendation.

### Orchestrator goal

The goal of the orchestrator is to ensure that the output of each agent is passed along in a format and sequence needed to fulfill the goal: Create the next evolution of the experience we are evaluating.

The orchestrator manages a **two-pass pipeline**:
1. **First pass:** 4A + 4B run in parallel, feeding into 4C for initial feature ranking
2. **Second pass:** 4D + 4E run in parallel on 4C's initial recommendations, then 4C re-ranks with feasibility and quality data

If subagents run into situations where they can't access or get behind certain forms or functions, the orchestrator can request help from the user to unblock the agents.

The final deliverable is a prioritized roadmap of UX/feature improvements with feasibility assessments.

### Final output format

The orchestrator produces **dual outputs**:

- **Markdown report** — structured document with all findings, recommendations, and pipeline data
- **Static HTML dashboard** — a self-contained HTML file with collapsible sections, filtering controls, and charts for interactive exploration of the results (no server required; opens in any browser)

### Decision-making guidance

Subagent issue resolution should be left up to the operator at this point, until we can figure out common issues to deal with.

---

## 4. Subagent Definitions

### 4A. Comparative Research Agent

**Purpose:** Analyze competitor and reference sites to identify patterns, trends, and opportunities the current site is missing.

**Inputs:**
Agent ingests from the config file the current experience code path or URL. The agent needs to figure out the appropriate sites to compare against based on the current codebase or URL, so it can determine the "right" sites to compare against. It is understood that the agent cannot fully evaluate experiences with just a URL because it won't be able to identify backend issues or architecture unless it has source code.

When competing sites are determined, they should be validated with the user and ranked in terms of their applicability so that the user can evaluate them.

- Specific aspects to compare:
  - Navigation pattern
  - Onboarding experience
  - Content strategy
  - Design
  - Interactivity
  - Accessibility
  - Content topic
  - Demographics of audience
  - User reviews

**Outputs:**
- Competitive feature matrix
- UX pattern catalog (what competitors do well)
- Gap analysis (what the current site lacks)
- Trend observations
- Relevant design systems based on semantic CSS or JavaScript information

**Guidance:**
Competitor/inspiration sites can optionally be provided via the config file. If not provided, the agent discovers them automatically based on site analysis.

---

### 4B. Code Analysis / Architecture Agent

**Purpose:** Analyze the local codebase to understand current architecture, patterns, tech debt, and extensibility. **This agent is also responsible for producing the complete tech stack analysis** that other agents rely on.

**Inputs:**
- Local codebase path (from config file)
- Key directories/files to focus on:
  - `src/components/`
  - `pages/`
  - `api/`

**Outputs:**
- **Tech stack analysis** — full technology inventory with UX-relevant pros/cons for each choice
- Architecture overview (component tree, data flow, routing)
- Mermaid diagrams
- Tech debt inventory
- Code quality assessment (patterns, anti-patterns)
- Extensibility report (how easy is it to add features X, Y, Z?)
- Interface flexibility, semantic tokens, theming
- Animations/interactions
- Bundle size and dependency analysis (feeds into 4E)

**Guidance:**
Derive any API documentation links or documentation that are collected. Include any information able to be collected about the componentized nature of the code, especially when it comes to interface elements.

---

### 4C. Feature Recommender Agent

**Purpose:** Synthesize findings from all other agents into prioritized feature/UX recommendations. Operates in a **two-pass mode**.

**Inputs:**

*Pass 1 (initial ranking):*
- Output from **4A** (Comparative Research)
- Output from **4B** (Code Analysis)
- User priorities (from config file)

*Pass 2 (re-ranking with feasibility and quality data):*
- Output from **4D** (Technology Feasibility) — feasibility ratings and cost estimates
- Output from **4E** (Quality Audit) — accessibility and performance findings
- Its own Pass 1 recommendations

**Outputs:**
- Ranked list of recommended improvements (final ranking after both passes)
- For each recommendation: description, rationale, estimated complexity, expected impact
- Quick wins vs. long-term investments
- Score breakdown per recommendation: user value, novelty, feasibility

**Guidance:**
Features are measured on three axes: **value to user**, **novelty to the market**, and **overall feasibility**. Higher value and higher feasibility are prioritized.

In Pass 1, the agent produces an initial ranking based on user value and novelty (feasibility is estimated). In Pass 2, the agent re-ranks using actual feasibility scores from 4D and quality findings from 4E, which may promote or demote recommendations.

---

### 4D. Technology Feasibility Agent

**Purpose:** Evaluate whether the current stack can support proposed recommendations, and identify what needs to change. Even if features can't be implemented on the current platform, we need to know overall how hard they would be to implement.

**Inputs:**
- Output from **4C Pass 1** (Feature Recommender's initial, pre-feasibility recommendations)
- Output from **4B** (Code Analysis — architecture details)
- Tech constraints (from config file, if any)

**Outputs:**
- Feasibility rating per recommendation (easy / moderate / hard / requires migration)
- **Cost estimates in developer-days:**
  - Small: 1-2 developer-days
  - Medium: 1-2 developer-weeks
  - Large: 1+ developer-months
- Required new dependencies or services
- Migration paths if stack changes are needed
- Risk assessment
- **Pro/cons analysis for each proposed change**

**Guidance:**
Regardless of recommendation, we need to show pros/cons for changes and include estimated cost of change in developer-day units.

---

### 4E. Quality Audit Agent

**Purpose:** Combined accessibility and performance audit of the current site. Provides quality baseline data that feeds into the Feature Recommender's second pass.

**Inputs:**
- Codebase analysis from **4B** (component structure, bundle info)
- Live URL from config file (for runtime auditing)

**Outputs:**
- **Accessibility report:**
  - WCAG 2.1 AA/AAA compliance assessment
  - Keyboard navigation audit
  - Color contrast check across all pages/states
  - Screen reader compatibility findings
  - ARIA usage review
- **Performance report:**
  - Core Web Vitals (LCP, FID/INP, CLS)
  - Bundle size analysis and tree-shaking opportunities
  - Image optimization assessment
  - Critical rendering path analysis
  - Caching strategy evaluation
- Priority list of quality issues ranked by user impact

**Guidance:**
Focus on issues that directly affect user experience. Flag critical accessibility violations separately from nice-to-have improvements. Performance data should include specific metrics where possible, not just qualitative assessments.

---

## 5. Subagent Pipeline / Data Flow

> The orchestrator manages a two-pass pipeline with parallel execution where possible.

```
┌──────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│                                                                  │
│  ┌─── Pass 1 ───────────────────────────────────────────────┐    │
│  │                                                          │    │
│  │  1. Launch in parallel:                                  │    │
│  │     ┌──────────────────┐  ┌──────────────────────┐       │    │
│  │     │ 4A. Comparative  │  │ 4B. Code Analysis    │       │    │
│  │     │     Research     │  │     / Architecture   │       │    │
│  │     └────────┬─────────┘  └──────────┬───────────┘       │    │
│  │              │                       │                   │    │
│  │              └───────────┬───────────┘                   │    │
│  │                          ▼                               │    │
│  │              ┌──────────────────────┐                    │    │
│  │              │ 4C. Feature          │                    │    │
│  │              │     Recommender      │                    │    │
│  │              │   (Initial Ranking)  │                    │    │
│  │              └──────────┬───────────┘                    │    │
│  └──────────────────────────┼───────────────────────────────┘    │
│                             │                                    │
│  ┌─── Pass 2 ───────────────┼───────────────────────────────┐    │
│  │                          ▼                               │    │
│  │  2. Launch in parallel on 4C's initial recommendations:  │    │
│  │     ┌──────────────────┐  ┌──────────────────────┐       │    │
│  │     │ 4D. Technology   │  │ 4E. Quality Audit    │       │    │
│  │     │     Feasibility  │  │  (A11y + Perf)       │       │    │
│  │     └────────┬─────────┘  └──────────┬───────────┘       │    │
│  │              │                       │                   │    │
│  │              └───────────┬───────────┘                   │    │
│  │                          ▼                               │    │
│  │              ┌──────────────────────┐                    │    │
│  │              │ 4C. Feature          │                    │    │
│  │              │     Recommender      │                    │    │
│  │              │   (Re-rank w/        │                    │    │
│  │              │    feasibility +     │                    │    │
│  │              │    quality data)     │                    │    │
│  │              └──────────┬───────────┘                    │    │
│  └──────────────────────────┼───────────────────────────────┘    │
│                             ▼                                    │
│              ┌──────────────────────┐                            │
│              │   Final Synthesis    │                            │
│              │   & Recommendations  │                            │
│              │  (Markdown + HTML)   │                            │
│              └──────────────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
```

**Summary flow:**
```
4A + 4B (parallel) → 4C (initial pass) → 4D + 4E (parallel) → 4C (re-rank) → Final Synthesis
```

---

## 6. Additional Context

### Competitor / inspiration sites

Provided at runtime via the config file (`competitor_urls` field) or discovered automatically by the 4A agent. Users can also provide these interactively when the agent asks for validation.

### Known pain points

Provided at runtime via the config file (`known_issues` field) or discovered by agents during analysis. The 4E (Quality Audit) agent will independently surface performance and accessibility pain points.

### Recent user feedback

Can be provided via the config file (`user_feedback` field) or supplied interactively when agents request it.

### Design assets / brand guidelines

Can be provided via the config file (`design_assets` field) if available. Agents will also attempt to extract design tokens and brand patterns from the codebase.

---

## 7. Configuration File Specification

The `analysis-config.yml` file is the primary way to provide runtime inputs to the agent system. The orchestrator reads this file before launching any subagents.

### Schema

```yaml
# analysis-config.yml

# === Required (at least one of target_path or target_url) ===
target_path: ""          # Absolute path to the local codebase
target_url: ""           # Public URL of the live site

# === User priorities (at least one required) ===
priorities:
  - "Better UX and new features"
  - "Performance and accessibility"
  - "Design system flexibility"

# === Optional ===
site_name: ""            # Human-readable name (derived from codebase if omitted)
site_description: ""     # One-sentence description (derived if omitted)

competitor_urls:         # Manually specified competitors (auto-discovered if omitted)
  - ""

known_issues:            # Known pain points to prioritize
  - ""

user_feedback: ""        # Paste or path to user feedback data

design_assets:           # Paths or URLs to design system / brand docs
  - ""

output_directory: "./output"   # Where to write the Markdown report and HTML dashboard

# === Constraints (optional) ===
constraints:
  must_keep: []          # Technologies or patterns that must not change
  must_avoid: []         # Technologies or approaches to avoid
  budget: ""             # e.g., "small team, 2-week sprint"
```

### Example

```yaml
# analysis-config.yml — example for a Next.js blog

target_path: "/home/user/projects/my-blog"
target_url: "https://myblog.example.com"

priorities:
  - "Mobile experience and performance"
  - "Accessibility compliance (WCAG 2.1 AA)"
  - "Modern design refresh"

site_name: "My Tech Blog"

competitor_urls:
  - "https://dev.to"
  - "https://hashnode.com"

known_issues:
  - "Slow initial page load on mobile"
  - "No dark mode support"
  - "Poor keyboard navigation in article list"

output_directory: "./evolution-report"

constraints:
  must_keep:
    - "Next.js framework"
    - "Vercel hosting"
  budget: "1 developer, 4-week sprint"
```

---

## Checklist

- [x] Section 1 — Website context defined as runtime inputs
- [x] Section 2 — Vision, priorities, and constraints finalized
- [x] Section 3 — Orchestrator goal, two-pass flow, and dual output format defined
- [x] Section 4A — Comparative Research Agent defined
- [x] Section 4B — Code Analysis Agent defined (includes tech stack responsibility)
- [x] Section 4C — Feature Recommender Agent defined (two-pass behavior)
- [x] Section 4D — Technology Feasibility Agent defined (developer-day costs, pro/cons)
- [x] Section 4E — Quality Audit Agent defined (accessibility + performance)
- [x] Section 5 — Pipeline flow with two-pass diagram confirmed
- [x] Section 6 — Additional context marked as runtime-provided
- [x] Section 7 — Configuration file schema and example provided
