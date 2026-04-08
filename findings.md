# Findings

## Current Project Reality

### Core exploration model
- The engine is not a generic agent loop; it is a deterministic route-first exploration pipeline
- Only `ROUTE` targets enter the BFS frontier
- Page-local interactions such as dropdown items, tabs, add modals, and expanded rows are explored inline after a route is captured

### Current strengths
- Strong artifact discipline already exists: screenshots, HTML snapshots, inventory, sitemap, run log, analysis
- The project is well-suited to admin/SaaS/backoffice environments
- DOM fingerprinting and novelty scoring already reduce redundant captures
- The current codebase is more explainable and reproducible than prompt-first browser agents

### Current gap relative to the new goal
- The system now outputs competitive-analysis artifacts, but live validation with a real vision provider is still pending
- Vision-assisted page understanding is integrated, but prompt quality and provider compatibility still need calibration on real targets
- Structured extraction exists for list/detail/form patterns, but heuristics still need tuning on representative admin/SaaS pages
- The competitive-analysis layer is functional, but final demo quality still depends on end-to-end validation and evidence quality checks

## Product Research Takeaways

### Stagehand
- Strongest idea to borrow: explicit high-level primitives such as observe/act/extract
- Best fit for this repo: clarify internal runtime boundaries, not switch to prompt-led control flow

### Browser Use
- Strongest idea to borrow: session and observability product mindset
- Best fit for this repo: better insight artifacts and run traceability

### Skyvern
- Strongest idea to borrow: computer-vision-based page understanding for messy frontends
- Best fit for this repo: visual page understanding in `OBSERVE`, not vision-led clicking

### Firecrawl
- Strongest idea to borrow: schema-first extraction and data-product framing
- Best fit for this repo: produce structured dataset artifacts instead of only reports

### OpenClaw
- Strongest idea to borrow: controlled browser-tool boundaries
- Best fit for this repo: keep execution deterministic and well-isolated

### Ponder
- Ponder appears more relevant as an artifact/workflow inspiration than as a browser-agent competitor
- Best fit for this repo: make outputs persistent, structured, and reusable for follow-up analysis

## Architecture Decisions for This Upgrade

### Vision role
- Chosen role: vision-enhanced discovery, not vision fallback, not vision-led execution
- Reason: fallback thresholds are ambiguous, while a fixed vision step in `OBSERVE` is easier to reason about and evaluate

### Vision input shape
- Screenshot + URL + lightweight DOM summary
- Avoid sending full HTML in v1 to control cost and complexity

### Vision output shape
- Structured JSON only
- Minimum fields:
  - `page_type`
  - `confidence`
  - `regions`
  - `interaction_hints`
  - `extraction_hints`
  - `notes`

### Vision merge strategy
- DOM remains the primary source of executable candidates
- Vision is used to:
  - annotate page semantics
  - rerank DOM-derived route candidates
  - guide later extraction strategy

### Skillization boundary
- Good future skill candidates:
  - `competitive-analysis-review`
  - `browser-agent-benchmark`
- Not suitable as skills:
  - browser execution
  - vision API runtime calls
  - extraction engine
  - artifact persistence
  - candidate reranking logic

## Code Changes Completed So Far
- Added `vision` config skeleton in `src/config.py` and `config/settings.yaml`
- Added artifact manager support for:
  - `output/artifacts/vision/`
  - `output/artifacts/page_insights/`
- Added typed models in:
  - `src/vision/types.py`
  - `src/analysis/competitive_report.py`
- Added prompt and placeholder client in:
  - `src/vision/prompts.py`
  - `src/vision/client.py`
- Added implementation breakdown file:
  - `COMPETITIVE_ANALYSIS_IMPLEMENTATION_PLAN.md`
- Integrated vision-aware observation into `src/agent/engine.py`
- Added lightweight DOM summary generation during `OBSERVE`
- Added per-page insight persistence and report-level page semantics summary
- Added structured extraction subsystem in `src/extraction/`
- Hooked extraction into route capture flow after page analysis
- Added dataset artifacts:
  - `dataset.jsonl`
  - `dataset_summary.json`
  - `extraction_failures.json`
- Added competitive-analysis generator and final outputs:
  - `competitive_analysis.json`
  - `competitive_analysis.md`

## Runtime Integration Notes

### What is implemented now
- During `OBSERVE`, the engine now:
  - extracts DOM candidates
  - builds a lightweight DOM summary
  - calls the vision client when `vision.enabled = true`
  - persists page insight artifacts
  - reranks route candidates using page-type hints

## Review Fixes Applied

### Page-type fallback
- The runtime, exploration report, and competitive-analysis layer now explicitly fall back from `page_type_vision = "unknown"` to DOM-derived page type
- This prevents `unknown` from overwriting valid DOM classifications in extraction and final reporting

### Interaction extraction
- Captured interaction states now flow through structured extraction, not only analyzer output
- This improves coverage for modal, tabbed, drawer, and inline-detail workflows

### Vision payload control
- Vision understanding now uses viewport screenshots instead of full-page screenshots
- The client also resizes screenshots to respect `vision.max_image_side` before upload

### Competitive-analysis cleanup
- `feature_modules` no longer mixes internal extraction strategy names into module inference
- Report and competitive-analysis aggregation now deduplicate page insights by URL, preferring captured states over `observe_*` placeholders

## Additional Pre-Flight Review Findings

### SPA/hash-route module inference is still too weak
- Fixed by teaching `competitive_report.py` to derive module paths from hash-router fragments before falling back to `urlparse(url).path`

### Interaction extraction still loses interaction identity
- Fixed by adding `capture_label` and `capture_context` to extraction artifacts
- This now preserves which tab, dropdown item, modal, or route produced each extracted result

### Vision cost can still spike during extraction-heavy runs
- Reduced by making interaction-derived extraction fall back to DOM-only page understanding instead of always invoking multimodal vision
- Route captures still use vision when enabled; interaction captures now avoid unnecessary extra API calls
- The runtime still keeps route discovery DOM-first
- Vision is advisory and does not create new executable selectors

### Current limitation
- `VisionClient` now supports an OpenAI-compatible multimodal chat-completions path
- It resolves credentials from `VISION_API_KEY` or the configured env var
- It still degrades safely when:
  - provider is unsupported
  - API key is missing
  - network/API request fails
  - JSON parsing fails
- Runtime network behavior has not yet been live-validated in this session

## Vision Provider Notes
- Current provider path: OpenAI-compatible `/chat/completions`
- Current payload style:
  - system prompt
  - user text prompt
  - inline `data:image/png;base64,...` screenshot
  - `response_format: json_object`
- Current implementation intentionally avoids adding a new SDK dependency
- This keeps setup lighter, but means compatibility depends on provider support for OpenAI-style vision chat payloads

## Open Decisions Still Ahead
- Exact vision provider API integration details
- Final page insight schema used by reranking and extraction
- Extraction confidence and failure taxonomy refinement
- Final competitive-analysis scoring/summary heuristics

## Extraction Design Notes
- Extraction currently runs only on captured route pages
- The dispatcher uses page insight strategy:
  - `list_table`
  - `detail_fields`
  - `form_schema`
- Empty results are preserved as artifacts instead of being silently discarded
- This keeps the system auditable and useful for later competitive-analysis synthesis
- Captured route pages now generate a page insight on demand before extraction if one does not already exist
- This prevents extraction from falling back to `unknown` strategy simply because `OBSERVE` has not revisited that route yet

## Competitive Analysis Layer Notes
- Competitive analysis is now generated from:
  - runtime state
  - page insights
  - extraction results
  - analysis results
- Current summary includes:
  - product category guess
  - admin maturity score
  - data density score
  - workflow complexity score
  - observed strengths and gaps
  - key differentiators
- Current implementation is heuristic but already produces structured outputs suitable for iteration
