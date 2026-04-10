# Progress Log

## Current Status

- Project has moved from a deterministic admin-dashboard crawler toward a browser agent tailored for competitive-analysis evidence collection.
- Core runtime, extraction, reporting, and first-pass auth flows are all implemented.
- Recent work focused on demo hardening, route quality, screenshot/report usefulness, human-assisted auth/challenge handling, and making public multi-site runs easier to execute.

## Major Completed Milestones

### Foundation

- Built the state-machine runtime, artifact system, analyzer, CLI, and BFS-style exploration baseline.
- Added route deduplication, novelty scoring, coverage tracking, and structured run logs.

### Competitive-Analysis Pivot

- Added DOM summary plus optional vision understanding.
- Added page insights and route reranking.
- Added structured extraction outputs:
  - `dataset.jsonl`
  - `dataset_summary.json`
  - `extraction_failures.json`
- Added competitive-analysis outputs:
  - `competitive_analysis.json`
  - `competitive_analysis_structured.md`
  - `competitive_analysis_readable.md`
  - optional synthesized `competitive_analysis.md`

### Agentic Runtime Upgrades

- Added goal-aware decision prioritization.
- Added action-outcome validation.
- Added site memory.
- Added re-observation after meaningful state changes.
- Added challenge detection with human-assisted pause/resume.
- Added first-pass registration and magic-link verification handling.

### Demo Hardening

- Added architecture decision log.
- Added readable screenshot-rich report generation.
- Added run profiles and timing summaries.
- Added batch multi-site execution and comparison reporting.
- Broadened route discovery beyond top-nav-only extraction.

### Recent Follow-Up Fixes

- Kept cheap nav extraction active on later pages while caching only expensive hover-menu discovery.
- Normalized deferred-route policy terms so auth-intent phrasing matches more reliably.
- Replaced unconditional pre-observe overlay closing with lightweight overlay triage.
- Removed forced visible-browser mode so configured headless runs can work again.
- Added bounded site concurrency for batch public runs with isolated per-site output roots.
- Added shared vision-request throttling to reduce API/network contention during concurrent runs.
- Added CLI support for passing one to three target URLs directly without writing a dedicated batch config.

## Latest Validation

- Latest compile check: `python -m compileall src` passed.
- No full automated regression suite exists yet.

## Recommended Next Work

- Prepare the external report / discussion brief around:
  - evidence-backed competitive-analysis positioning
  - improved report insight quality
  - public multi-site runner ergonomics
- Run fresh smoke tests for:
  - ad-hoc multi-URL public mode
  - public `artificialanalysis` demo config
  - registration-oriented `artificialanalysis` config
- Improve comparison-report quality against human-written analyst outputs.

## Latest Note

- Simplified `findings.md`, `progress.md`, and `task_plan.md` into concise working-memory files.
- Reviewed `D:\web_access\web-access` as an external reference.
- Main conclusion:
  - its strongest ideas are proxy/bootstrap ergonomics and domain experience reuse
  - its CDP proxy model is materially different from the repo's current isolated Playwright-runner architecture
- Improved competitive-analysis reporting without changing the crawler first.
  - added a richer structured analysis layer:
    - product thesis
    - route-family distribution
    - primary entry points
    - product pillars
    - coverage caveats
  - rewrote the readable report to emphasize:
    - what the product appears to be
    - why that judgment is supported
    - where the current crawl is biased
  - added `python -m src.tools.regenerate_reports` so reports can be regenerated directly from existing artifacts
- Validated the new reporting layer against the existing `artificialanalysis.ai` outputs.
  - compile passed
  - offline report regeneration succeeded
  - regenerated report now reads `artificialanalysis.ai` as an `analysis_portal` instead of `developer_docs`
- Improved public runner ergonomics without changing the engine core.
  - restored true headless support
  - added bounded multi-site public concurrency
  - isolated artifacts per site within batch runs
  - throttled vision concurrency across concurrent runs
  - added CLI ad-hoc URL mode for 1-3 targets
- Latest local validation:
  - `python -m compileall src` passed after the CLI and runner changes
