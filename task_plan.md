# Task Plan: Competitive Analysis Frontend Recon Agent

## Goal
Evolve `frontend_recon_agent` from a deterministic website exploration framework into a competitive-analysis pipeline that can:

- accept a target URL and competitive-analysis intent
- explore and capture the site with evidence
- use vision-assisted page understanding during observation
- extract structured data from key page types
- generate reusable competitive-analysis artifacts and reports

## Current Phase
Phase 7 - Validation and quality hardening

## Phases

### Phase 0: Existing Recon Framework Baseline
- [x] Review current project architecture and runtime behavior
- [x] Confirm current route-first BFS exploration model
- [x] Confirm current artifacts, analyzer, and logging capabilities
- **Status:** complete

### Phase 1: Product Direction and External Research
- [x] Define new end goal as competitive analysis, not generic browser automation
- [x] Research browser-agent product patterns across Stagehand, Browser Use, Skyvern, Firecrawl, OpenClaw
- [x] Clarify Ponder as artifact/workflow inspiration rather than direct browser-agent competitor
- [x] Write implementation strategy and comparison framing
- **Status:** complete

### Phase 2: Planning and Implementation Breakdown
- [x] Create a concrete implementation breakdown in `COMPETITIVE_ANALYSIS_IMPLEMENTATION_PLAN.md`
- [x] Record vision-augmented discovery as the first major increment
- [x] Record two future skill candidates:
  - `competitive-analysis-review`
  - `browser-agent-benchmark`
- **Status:** complete

### Phase 3: Vision Foundation
- [x] Add `vision` configuration section
- [x] Add vision artifact directories and save helpers
- [x] Add typed models for vision results and page insights
- [x] Add prompt builder and placeholder vision client
- [x] Integrate vision into `OBSERVE`
- [x] Generate DOM summary for multimodal calls
- [x] Persist per-page vision artifacts during real runs
- [x] Replace placeholder vision client with real OpenAI-compatible API path
- **Status:** in_progress

### Phase 4: Page Insight and Candidate Reranking
- [x] Create per-page insight artifacts that merge DOM and vision understanding
- [x] Add route-candidate reranking rules driven by page type and regions
- [ ] Preserve route frontier semantics while improving prioritization
- **Status:** pending

### Phase 5: Structured Extraction
- [x] Add extraction subsystem
- [x] Implement list/table extractor
- [x] Implement detail/key-value extractor
- [x] Implement form/schema extractor
- [x] Emit `dataset.jsonl`, `dataset_summary.json`, `extraction_failures.json`
- **Status:** complete

### Phase 6: Competitive Analysis Artifacts
- [x] Add `competitive_analysis.json`
- [x] Add `competitive_analysis.md`
- [x] Aggregate evidence-backed feature, entity, and workflow findings
- [x] Ensure the report is readable without raw log inspection
- **Status:** complete

### Phase 7: Validation and Demo Readiness
- [x] Fix page-type fallback so report/extraction layers do not get stuck on `unknown`
- [x] Include interaction captures in structured extraction
- [x] Honor `vision.max_image_side` and use viewport screenshots for vision understanding
- [x] Remove internal extraction strategy names from competitive-analysis module inference
- [x] Deduplicate page-insight aggregation by URL in report and competitive-analysis layers
- [x] Preserve interaction identity in extraction artifacts
- [x] Improve feature-module inference for hash-routed admin SPAs
- [x] Reduce vision-call amplification by using DOM-only page understanding for interaction captures
- [ ] Verify the system still runs when vision is disabled
- [ ] Verify the system degrades gracefully when vision API fails
- [ ] Test on at least one representative admin/SaaS target
- [ ] Confirm final output is stronger than a generic browser-agent transcript for competitive analysis
- **Status:** in_progress
