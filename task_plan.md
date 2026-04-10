# Task Plan

## Goal

Ship `frontend_recon_agent` as a credible competitive-analysis demo built on a Playwright-based browser agent runtime.

## Current Phase

Phase 16 - Report preparation and demo framing

## Current Architecture

- Browser runtime: Playwright, local browser with configurable visible/headless mode
- Control loop:
  - observe
  - decide
  - act
  - re-observe
- Main outputs:
  - screenshots and DOM snapshots
  - page insights and extraction artifacts
  - readable competitive-analysis reports
  - optional synthesized narrative report

## Completed Phases

### Phase 0 - Baseline Runtime
- [x] Confirm original BFS exploration framework
- [x] Confirm artifact, analyzer, and CLI foundations
- **Status:** complete

### Phase 1 - Competitive-Analysis Pivot
- [x] Reframe the project around evidence-backed competitive analysis
- [x] Add vision-aware page understanding and page insights
- [x] Add structured extraction and report-generation layers
- **Status:** complete

### Phase 2 - Agentic Runtime Upgrade
- [x] Add goal-aware decisions
- [x] Add action validation and site memory
- [x] Add re-observation after state changes
- [x] Add challenge handling and human assistance paths
- **Status:** complete

### Phase 3 - Demo Hardening
- [x] Add readable screenshot-rich report output
- [x] Add batch orchestration and comparison reporting
- [x] Add timing summaries and improved route discovery
- [x] Add first-pass registration / magic-link continuation support
- **Status:** complete

### Phase 4 - Review and Stabilization
- [x] Run a focused project code review
- [x] Fix nav-discovery over-pruning
- [x] Fix deferred-route goal matching brittleness
- [x] Replace unconditional overlay dismissal with overlay triage
- **Status:** complete

## Recent Completed Phases

### Phase 13 - External Reference Review and Architecture Comparison
- [x] Inspect `D:\web_access\web-access`
- [x] Understand whether it uses proxy/API browser access rather than local Playwright control
- [x] Compare that model against the current runtime
- [x] Decide what ideas are worth borrowing without changing the browser foundation prematurely
- **Status:** complete

### Phase 14 - Report Insight Quality Improvement
- [x] Inspect current report generators against existing `artificialanalysis.ai` outputs
- [x] Identify why current reports feel low-conviction despite decent artifacts
- [x] Improve the structured competitive-analysis object with thesis, route-family distribution, product pillars, and coverage caveats
- [x] Rewrite the readable report to emphasize product judgment, evidence, and explicit caveats
- [x] Add offline report regeneration from existing artifacts
- [x] Validate the new report layer against existing `artificialanalysis.ai` outputs
- **Status:** complete

### Phase 15 - Public Runner Ergonomics and Concurrency Control
- [x] Remove forced `headless=False` overrides so browser mode can be configured again
- [x] Add bounded multi-site public concurrency for batch runs
- [x] Preserve independent per-site output roots inside batch execution
- [x] Add shared vision-request throttling for concurrent public runs
- [x] Add CLI support for launching one to three target URLs directly
- [x] Validate code completeness locally without rerunning live sites
- **Status:** complete

## Active Phase

### Phase 16 - Report Preparation and Demo Framing
- [ ] Update the discussion brief / report framing to reflect the current runtime more clearly
- [ ] Summarize the strongest evidence that the project is now more usable for public-site comparison runs
- [ ] Decide which residual risks to surface explicitly in the external report
- **Status:** in progress

## Open Risks

- Registration flow quality is still less proven than public-site analysis.
- Comparison reporting is better, but still needs calibration against strong human-written analyst memos.
- No automated regression suite exists for the runtime-critical paths.
- Competitive-analysis framing is still not fully consistent across all docs and outputs.
- The new direct-URL runner is convenient, but it still inherits the assumptions of the chosen base config template.

## Decision Filters

- Prefer borrowing ideas from external systems over replacing the runtime wholesale unless there is clear leverage.
- Preserve evidence quality and inspectability as first-class product traits.
- Avoid changes that make the demo look more agentic but less auditable.
