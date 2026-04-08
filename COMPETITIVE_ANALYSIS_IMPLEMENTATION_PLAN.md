# Competitive Analysis Implementation Plan

## Goal
Turn `frontend_recon_agent` from a website exploration tool into a competitive-analysis pipeline:

- Input: target URL + analysis intent
- Process: login, explore, capture, vision understanding, structured extraction
- Output: evidence-backed competitive analysis artifacts and report

This plan keeps the current `DOM-first` engine and adds vision and analysis as layered enhancements, not replacements.

## Principles
- Keep route discovery deterministic and `DOM-first`
- Use vision in `OBSERVE`, not as the click driver
- Make every important conclusion traceable to artifacts
- Prefer structured JSON outputs before polished prose
- Optimize first for admin/SaaS/backoffice sites

## The 3 Most Important Increments

### Increment 1: Vision-Augmented Page Understanding
Add a fixed vision step to each observed page so the system can classify page type, detect major regions, and enrich DOM-derived candidates.

Why first:
- It improves both exploration quality and later extraction
- It creates a strong product differentiator for the trial
- It does not require rewriting the core engine

Definition of done:
- Every visited page can optionally produce a vision JSON artifact
- Vision output includes `page_type`, `regions`, `interaction_hints`, `extraction_hints`
- The engine continues to work when the vision API fails or times out
- DOM candidate flow remains the primary path

Files to add:
- `src/vision/types.py`
- `src/vision/prompts.py`
- `src/vision/client.py`

Files to update:
- `src/config.py`
- `src/agent/engine.py`
- `src/artifacts/manager.py`
- `src/artifacts/report.py`

Implementation notes:
- Add a `vision` config section with `enabled`, `model`, `timeout_ms`, `max_image_side`, `artifact_dir`
- In `_phase_observe()`, after DOM extraction, capture a page screenshot and build a lightweight DOM summary
- Call the vision client with `screenshot + url + dom_summary`
- Save the result under `output/artifacts/vision/`
- Use the result to annotate the page and rerank route candidates, but do not create new executable selectors from vision

## Increment 2: Schema-First Structured Extraction
Add extraction that turns captured states into reusable data assets instead of only screenshots and page analysis.

Why second:
- This is what makes the system useful for actual competitive research
- It gives the final report something concrete beyond navigation and screenshots
- Vision output can directly guide extraction strategy

Definition of done:
- Each captured state can be assigned an extraction strategy
- The system supports at least 3 extractors:
  - list/table
  - detail/key-value
  - form/schema
- The run produces `dataset.jsonl`, `dataset_summary.json`, and `extraction_failures.json`

Files to add:
- `src/extraction/__init__.py`
- `src/extraction/types.py`
- `src/extraction/engine.py`
- `src/extraction/list_extractor.py`
- `src/extraction/detail_extractor.py`
- `src/extraction/form_extractor.py`

Files to update:
- `src/agent/engine.py`
- `src/analyzer/page_analyzer.py`
- `src/artifacts/manager.py`
- `src/artifacts/report.py`

Implementation notes:
- Use page insight to choose extraction strategy
- Initial mapping:
  - `list` -> list/table extractor
  - `detail` -> detail extractor
  - `form` or `modal` -> form extractor
- Extraction outputs should keep evidence references:
  - `state_id`
  - `url`
  - `page_type`
  - `evidence_paths`
- If extraction confidence is low, log a structured failure instead of silently skipping

## Increment 3: Competitive Analysis Report Layer
Add a top-level analysis layer that turns collected evidence and extracted data into a structured competitive analysis.

Why third:
- This is the final user-facing value proposition
- It makes the system directly comparable to general browser agent products
- It reframes the project around product understanding, not just crawling

Definition of done:
- The run generates `competitive_analysis.json`
- The run generates `competitive_analysis.md`
- The report includes evidence-backed claims, not just narrative summary
- The report is usable even when vision is partially unavailable

Files to add:
- `src/analysis/__init__.py`
- `src/analysis/competitive_report.py`

Files to update:
- `src/agent/engine.py`
- `src/artifacts/report.py`
- `README.md`

Implementation notes:
- Competitive analysis JSON should contain:
  - `target`
  - `run_metadata`
  - `site_structure_summary`
  - `page_type_distribution`
  - `feature_modules`
  - `data_entities`
  - `interaction_patterns`
  - `design_system_signals`
  - `evidence_index`
  - `competitive_summary`
  - `comparison_notes`
- Markdown report should contain:
  - Executive Summary
  - Site Architecture
  - Product Surface Overview
  - Core Modules and Evidence
  - Data Model and Entity Clues
  - Interaction and Workflow Complexity
  - UI and Design System Signals
  - Competitive Positioning
  - Open Questions

## Recommended Build Order

### Step 1: Config and types foundation
Do this before any deeper integration.

- Add `vision` config in `src/config.py`
- Add `vision` typed output models
- Add `page insight` and `competitive analysis` typed schemas
- Add output directory support for `vision`, `page_insights`, and final analysis artifacts

Completion check:
- The app loads with vision disabled by default
- Output directories are created without breaking current runs

### Step 2: Minimal vision client and artifact persistence
Build the thinnest possible end-to-end path.

- Implement prompt builder
- Implement client wrapper for external multimodal API
- Add safe parsing into typed vision output
- Persist `state_xxx_vision.json` artifacts

Completion check:
- One page can successfully produce a vision artifact
- Timeout or API failure does not stop the run

### Step 3: Observe-stage integration
Wire vision into the current engine at the right location.

- Insert vision after DOM candidate extraction in `_phase_observe()`
- Store per-page vision result in runtime state
- Add candidate reranking based on `page_type` and `regions`
- Keep route frontier semantics unchanged

Completion check:
- Current exploration still works
- Candidate order changes when vision signals are present
- No new route is created from vision alone

### Step 4: Page insight artifacts
Create a unified artifact that merges DOM and vision understanding.

- Produce `page_insight` JSON for each captured page
- Include:
  - `page_type_dom`
  - `page_type_vision`
  - `dom_component_types`
  - `vision_regions`
  - `interaction_hints`
  - `extraction_strategy`
  - `high_value_page`
  - `analysis_tags`

Completion check:
- Every captured route has a page insight artifact
- DOM/vision disagreement is visible in artifacts

### Step 5: Extraction engine
Implement extraction as a separate subsystem, not as ad-hoc logic inside report generation.

- Add extractor dispatch logic
- Implement list/table extraction
- Implement detail extraction
- Implement form/schema extraction
- Emit dataset and failures

Completion check:
- A standard admin list page produces rows and columns
- A detail page produces key-value data
- A modal or form produces field schema

### Step 6: Competitive report generation
Turn artifacts into a final product-facing deliverable.

- Aggregate feature modules from routes, insights, extraction, and analysis
- Infer likely product shape and data density
- Add evidence references for every major claim
- Save JSON and Markdown versions

Completion check:
- The final report can be read without opening raw logs
- Important claims can still be traced to screenshots or insights

## Candidate Reranking Rules
Use vision to rerank, not replace, DOM candidates.

- `dashboard`
  - prioritize navigation routes
  - lower weight for detail/form-heavy interpretation
- `list`
  - prioritize data-rich sections and row-action related areas
  - mark page as high-value for extraction
- `detail`
  - preserve related tabs and linked detail routes
- `form` or `modal`
  - prioritize schema extraction
- `filter_bar + table + pagination`
  - strongly mark as high-value operational page

These rules should affect candidate priority and page tags, not execution authority.

## Artifact Layout
Add these outputs without removing current ones:

- `output/artifacts/vision/`
- `output/artifacts/page_insights/`
- `output/artifacts/dataset.jsonl`
- `output/artifacts/dataset_summary.json`
- `output/artifacts/extraction_failures.json`
- `output/artifacts/competitive_analysis.json`
- `output/reports/competitive_analysis.md`

Current outputs to preserve:
- `inventory.json`
- `sitemap.json`
- `coverage.json`
- `run_log.jsonl`
- `analysis/*.json`
- `exploration_report.md`

## Comparison Strategy Against Existing Products
The final system should be framed as better for competitive analysis, not necessarily better for all browser automation.

Borrow intentionally:
- From Stagehand: clear internal primitives and observe-first design
- From Browser Use: session/observability mindset
- From Skyvern: visual understanding for messy frontends
- From Firecrawl: schema-first data extraction
- From Ponder: artifact-centric analysis outputs

Do not copy directly:
- black-box task loops as the only control flow
- vision-led clicking as the default execution path
- cloud-infra-heavy positioning for the trial version

## Skillization Opportunities
Two later-stage analysis loops are good candidates for dedicated LLM skills. They should consume artifacts produced by the codebase, not replace the runtime engine.

### Skill 1: `competitive-analysis-review`
Purpose:
- Read run artifacts and generate a structured competitive analysis
- Enforce consistent evidence-backed report structure
- Surface strengths, gaps, differentiators, and open questions

Inputs:
- `inventory.json`
- `sitemap.json`
- `coverage.json`
- vision artifacts
- page insights
- extracted dataset artifacts
- screenshots and reports as supporting evidence

Why it should be a skill:
- The workflow is mostly about interpretation and synthesis
- The same artifact-reading pattern will be reused across many targets
- It keeps analysis prompt logic out of the core runtime system

### Skill 2: `browser-agent-benchmark`
Purpose:
- Compare this system against products such as Stagehand, Browser Use, Skyvern, Firecrawl, OpenClaw, and Ponder-style artifact workflows
- Generate a structured benchmark matrix and positioning summary

Inputs:
- official docs or notes for benchmarked products
- local competitive analysis artifacts
- fixed comparison dimensions and reporting template

Why it should be a skill:
- Benchmarking is report-oriented and repeatable
- It benefits from a stable comparison rubric
- It is better as a reusable analysis layer than hard-coded runtime logic

Boundary rule:
- Skills should operate in the analysis/reporting layer
- Browser control, extraction, vision API calls, artifact persistence, and candidate reranking remain code responsibilities

## Acceptance Criteria
- Given a target URL, the system explores the site and captures evidence
- The system classifies pages with vision-enhanced understanding
- The system extracts structured data from key page types
- The system generates a competitive analysis report with evidence links
- The system remains usable when vision fails
- The resulting output is more structured, auditable, and reusable than a generic browser agent transcript

## Suggested Milestone Sequence for the Trial
- Milestone 1: vision artifacts generated and visible
- Milestone 2: page insight and extraction outputs working on one admin site
- Milestone 3: competitive analysis JSON and Markdown generated end-to-end

## Assumptions
- External multimodal API is available for the first version
- The first target class is admin/SaaS/backoffice products
- The current BFS route exploration model remains intact
- Visual understanding improves analysis quality, but does not replace deterministic navigation
