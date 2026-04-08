# Progress Log

## Session 1 - 2026-03-19
- Built initial project: login, BFS crawl, deep interaction, analysis, Vue generation
- Captured 68 pages/interactions from labverix.com
- Fixed 94 robustness issues

## Session 2 - 2026-03-22
- Major refactor: linear script to agent framework (v2.0)
- Built 7 phases: data models, execution, observation, engine, artifacts, analyzer, CLI
- Live testing revealed 3 bugs:
  1. Sub-menu titles matched as nav targets
  2. No deduplication by href caused frontier explosion
  3. Child menu-item filter skipped wrapped Element Plus nav items
- Fixed the above issues and completed a successful 100-state run
- Generated inventory, sitemap, run log, and exploration report

## Session 3 - 2026-04-08
- Re-read the codebase and confirmed the real runtime model:
  - route-first BFS
  - inline interaction exploration
  - novelty-gated interaction capture
- Shifted the project goal from generic recon to competitive-analysis generation
- Researched browser-agent and extraction products:
  - Stagehand
  - Browser Use
  - Skyvern
  - Firecrawl
  - OpenClaw
  - Ponder
- Defined the new positioning:
  - better for evidence-backed competitive analysis
  - not necessarily better for all browser automation
- Wrote `COMPETITIVE_ANALYSIS_IMPLEMENTATION_PLAN.md`
- Added two future skill candidates to the plan:
  - `competitive-analysis-review`
  - `browser-agent-benchmark`
- Implemented phase-1 foundation changes:
  - added `vision` config section
  - added `vision` and `page_insights` artifact directories
  - added typed vision and competitive-analysis models
  - added prompt builder and placeholder vision client
- Implemented the first end-to-end vision-aware observation path:
  - DOM summary generation in `OBSERVE`
  - conditional vision call during observation
  - page insight generation and persistence
  - basic route reranking using page-type hints
  - page semantics section in `exploration_report.md`
- Replaced the placeholder vision client with a real OpenAI-compatible multimodal request path
- Added environment/config support for:
  - `VISION_API_KEY`
  - `VISION_API_BASE_URL`
  - configured `vision.api_key_env`
- Built the structured extraction subsystem:
  - list/table extractor
  - detail/key-value extractor
  - form/schema extractor
  - extraction dispatcher
- Wired extraction into the route capture lifecycle
- Added dataset artifacts and report summary for extraction outputs
- Added the competitive-analysis generator layer
- Wired finalize to emit:
  - `competitive_analysis.json`
  - `competitive_analysis.md`
- Added heuristic product/category scoring and evidence aggregation
- Fixed route extraction timing by generating a page insight on demand before extraction when needed
- Updated README and `settings.local.yaml.example` to reflect vision, extraction, and competitive-analysis capabilities
- Verified the codebase still compiles with `python -m compileall src`
- Ran a focused code review and fixed the highest-value issues:
  - corrected fallback from `page_type_vision = "unknown"` to DOM page types
  - routed interaction captures through structured extraction
  - switched vision understanding to viewport screenshots and enforced image resizing via `vision.max_image_side`
  - removed internal extraction strategy names from competitive-analysis module inference
  - deduplicated page insights by URL in report and competitive-analysis aggregation
  - cleaned up duplicate `capture_viewport_screenshot()` definitions introduced during patching
- Re-verified the codebase compiles with `python -m compileall src`
- Ran a second pre-flight review and recorded remaining risks around:
  - hash-route module inference for SPA-style admin products
  - missing interaction identity in extraction artifacts
  - potential vision-call amplification during interaction-heavy runs
- Fixed that second review pass by:
  - deriving feature modules from hash-router fragments when present
  - adding `capture_label` / `capture_context` to extraction outputs
  - making interaction extraction use DOM-only page understanding to avoid redundant multimodal calls
- Re-verified the codebase compiles with `python -m compileall src`

## Next Up
- Live-validate the vision provider path with a configured API key
- Improve reranking and page-type heuristics using actual vision output
- Validate end-to-end output quality on a representative admin/SaaS target
