# Task Plan: General Browser Agent Pivot

## Goal
Evolve `frontend_recon_agent` from a deterministic exploration framework into a more general browser agent that can:

- accept a target URL and high-level task intent
- complete multi-step website onboarding flows such as registration and guided entry
- browse and understand product surfaces across a broader range of websites, not only admin dashboards
- handle more dynamic flows with repeated page understanding and step-by-step control
- preserve evidence and structured outputs for downstream competitive analysis when useful

## Current Phase
Phase 11 - Demo-oriented competitive-analysis hardening

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
- [x] Create and maintain a single combined direction + implementation document in `DISCUSSION_BRIEF.md`
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
- [x] Add optional LLM synthesis layer for the final competitive-analysis report
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
- [x] Test on at least one representative general website target
- [x] Confirm final output is stronger than a generic browser-agent transcript for competitive analysis
- **Status:** in_progress

### Phase 8: General Browser-Agent Pivot
- [ ] Reframe system from `DOM-grounded competitive-analysis pipeline` to `general browser agent with evidence outputs`
- [x] Record borrow points from `web-access` while keeping Playwright as the browser runtime
- [x] Add goal-driven decision prioritization instead of pure FIFO step execution
- [x] Add validate-after-action checks so clicks and submits must show meaningful state change
- [x] Add first-pass site memory so the run can remember what works on the current domain
- [x] Reduce reliance on route-first DOM discovery as the only decision source by adding page-level decision planning
- [x] Design repeated page-understanding / re-observation triggers after key state changes
- [x] Add first-pass support for broader end-to-end flows such as form fill and submit
- [x] Define first-pass approach for captcha / anti-bot detection and pause-and-report handling
- [x] Select a simple public website for first live API smoke test
- [x] Add a smoke-test runbook for the first live validation pass
- [x] Run a minimal external smoke test with the newly obtained API key
- [x] Standardize `vision.model` to `gpt-5.4`
- **Status:** in_progress

### Phase 9: Evidence-Quality Validation
- [x] Define an explicit comparison frame between plain browser transcripts and this repo's evidence outputs
- [x] Inspect current artifact/report structure against that comparison frame
- [x] Identify the weakest gaps for general-website competitive analysis
- [x] Implement the highest-value reporting or aggregation improvements if needed
- [x] Document the proof points and remaining limitations
- **Status:** in_progress

### Phase 10: Evidence Schema Refactor
- [x] Define a concrete `EvidenceUnit` shape inside extraction outputs
- [x] Split general-site content extraction into collectors, normalization, and assembly steps
- [x] Preserve anchored page evidence in `dataset.jsonl`
- [x] Surface page-level evidence samples in competitive-analysis reporting
- [x] Reduce over-collection and low-value navigation noise, especially social/utility/auth duplicates
- [ ] Improve remaining mojibake cleanup for a few stubborn strings
- **Status:** in_progress

### Phase 11: Demo-Oriented Competitive Analysis Hardening
- [x] Add an explicit architecture-decision log so each major technical choice has rationale and rejected alternatives
- [ ] Reframe acceptance criteria and report wording fully around competitive analysis, not general browsing completeness
- [x] Upgrade report generation from engineering summaries into genuinely human-readable competitive-analysis deliverables
- [ ] Design and implement a three-mode access model:
  - public / no-login
  - existing-account login
  - email registration then login / entry
- [x] Add multi-target orchestration so independent site runs can execute concurrently and emit:
  - site A report
  - site B report
  - comparison report
- [x] Revisit default exploration budgets for demo realism; stop treating `max_states=6` style smoke runs as representative
- [x] Decide whether single-site exploration should stay single-threaded or gain bounded parallel page exploration
- [x] Add screenshot-selection policy based on novelty and evidence value instead of dumping every capture equally into reporting
- [x] Insert selected screenshots into final human-readable reports with evidence-aware captions
- [x] Separate run profiles so smoke, demo, and full analysis no longer share the same heavy path by default
- [x] Emit timing summaries so slow runs can be diagnosed by phase and action instead of guesswork
- [ ] Define an evaluation workflow against human-written competitive-analysis reports
- [ ] Validate the `register` access mode against a realistic external target rather than relying on local mock coverage
- [ ] Rework the comparison report using human-written comparison memos as the benchmark for readability and usefulness
- [ ] Validate screenshot-ranking usefulness with a small human-judged sample rather than novelty heuristics alone
- [x] Add a first-pass human-assisted verification path so email signup can pause for manual code entry/resume instead of failing immediately
- [x] Extend auth handling to cover unified email-entry / magic-link sites such as `artificialanalysis.ai`
- **Status:** in_progress

## Current Proof Points
- `run_log.jsonl` records step execution, but not reusable product structure
- `page_insights` now preserve general-site page semantics such as `landing`, `content`, and `docs`
- `dataset.jsonl` now captures structured `content_blocks` evidence including hero titles, CTAs, nav items, and content sections
- `competitive_analysis.json/.md` aggregate those signals into category guesses, strengths, gaps, differentiators, and evidence index entries
- A 2026-04-09 live run against `python.org` produced 6 route captures and 4 successful `content_blocks` extractions
- A later 2026-04-09 refactor pass upgraded `dataset.jsonl` to include `evidence_units` with anchors such as `locator`, `dom_path`, `html_fragment`, and `screenshot_ref`
- A later 2026-04-09 validation pass fixed route resolution for relative navigation targets, so `Downloads` and `About` now resolve to `www.python.org` pages instead of incorrect `docs.python.org/...` 404 routes
- The same pass reduced discovered targets from 14 to 12 and improved extraction results from 4 successful / 2 empty to 5 successful / 1 empty
- A final 2026-04-09 evidence pass tightened nav collection to top-level navigation and removed social/auth duplication from `dataset.jsonl`, reducing `nav_item_count` from 16 to 12 on the representative `python.org` pages
- A later 2026-04-09 generalization pass improved `content_section` coverage substantially on `python.org` content pages, while also replacing lingering admin-centric scoring/report wording with more general application-surface language
- A later 2026-04-09 vision-assisted docs pass used existing vision hints to rescue weak docs-section extraction on `https://docs.python.org/3/`, improving that page from `0 sections` to `10 sections` in a docs-only smoke test
- The current implementation already demonstrates a grounded evidence pipeline for single-site competitive-analysis demo runs on public websites

## New Scope From Latest Leader Sync
- Every major technical decision should be justified with explicit rationale and rejected alternatives
- The project should be presented first and foremost as a competitive-analysis demo, not a generic browser agent demo
- Demo-time access support should include exactly three paths:
  - no-login public browsing
  - existing-account login
  - email registration flow leading into logged-in browsing
- Multi-site requests such as "analyze site A and site B" should run concurrently rather than serially when targets are independent
- Final readable reports should become image-rich:
  - select high-value screenshots
  - place them near the relevant text evidence
  - improve comparability with human-written reports

## Rationale Discipline
- For all upcoming architectural changes, capture:
  - chosen approach
  - why it fits demo and competitive-analysis goals
  - why obvious alternatives were not selected yet
- Candidate areas where rationale is especially important:
  - why keep Playwright instead of switching orchestration frameworks
  - why support only three access modes for demo scope
  - why use concurrent independent runs instead of one shared browser swarm
  - why keep or avoid parallel exploration within a single website
  - why prefer evidence-triggered screenshot insertion over full visual dumping
  - why compare against human-written reports at the evaluation layer rather than directly in the runtime loop

## Latest Implementation Update
- Added `ARCHITECTURE_DECISIONS.md` with explicit ADR-style rationale for:
  - human-readable reporting
  - budget tiers
  - concurrency sequencing
  - screenshot selection
- Expanded `ARCHITECTURE_DECISIONS.md` to also justify:
  - demo-scoped access modes
  - independent multi-site concurrency with post-run comparison
  - runtime profiles plus timing summaries
- Added an explicit weak-justification section so temporary technical choices are recorded as provisional rather than overstated
- Added `competitive_analysis_readable.md` as a new stakeholder-facing output
- The readable report now:
  - selects a bounded set of screenshots
  - prefers page-type diversity plus evidence density
  - embeds images directly in markdown with contextual captions
- The readable report now also prefers report-specific viewport screenshots for most pages while keeping full-page captures as archival evidence
- Added `config/smoke_test_public_nosynth.yaml` for faster verification of report-generation changes without final LLM synthesis latency
- Added first-pass batch support through `--batch-config`, site-isolated outputs under `output/batch/...`, and a generated `comparison_report.md`
- Added a first-pass registration-oriented authenticator mode and local mock registration fixtures, but end-to-end browser validation against the local mock server is still incomplete
- Added `run`-level profile controls and `--profile` CLI support
- Implemented named profiles:
  - `default`
  - `smoke_fast`
  - `demo`
  - `full`
- Added `run_timing_summary.json` so the runtime now exposes where time was spent across initialize/authenticate/observe/execute/analyze/finalize
- Added a first-pass human-assisted verification path for registration:
  - detect OTP / verification pages
  - pause in terminal
  - accept manual code entry or manual browser completion
  - then continue the same run
- Enforced visible-browser operation for interactive auth/testing instead of relying on headless mode

## Current Rationale Watchlist
- Strongly justified enough for the current demo phase:
  - deterministic readable-report layer on top of structured evidence
  - multi-site concurrency via isolated per-site runs
  - profile separation between smoke/demo/full
  - viewport-oriented report images with archival full-page captures retained
- Shipped but still only weakly justified:
  - local mock registration as a proof target
  - selector-driven registration as anything more than a first-pass demo implementation
  - novelty as a screenshot-ranking factor without human usefulness calibration
  - current comparison-report structure as a final stakeholder-facing compare output

## Today Scope Update
- Skip `vision disabled` and `vision graceful degradation` validation for now
- Treat repeated vision/API failure as retriable runtime failure that should eventually surface an explicit error
- Use a representative general website rather than an admin/SaaS target
- Prioritize proving that final outputs are more useful for competitive analysis than a plain action transcript
- Keep the shared rule layer site-agnostic:
  - prefer structural heuristics over target-site strings
  - treat textual keywords as weak hints instead of hard gates when possible
  - do not patch benchmark-site quirks directly into shared extractor logic

## Emerging Priority Shift
- Public-site coverage on `artificialanalysis.ai` is currently bottlenecked by candidate discovery, not state budget
- Raising `max_states` from smoke-sized runs to a larger public run did not expand beyond 4 discovered route targets
- This elevates a new near-term improvement area:
  - strengthen generic route/candidate extraction for trigger-heavy marketing/content sites before spending more effort on even larger per-site budgets
