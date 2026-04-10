# Findings

## Project Snapshot

- Project: `frontend_recon_agent`
- Current positioning:
  - externally: competitive-analysis demo
  - internally: Playwright-based browser agent with evidence outputs
- Current runtime shape:
  - route-first frontier plus page-level decisions
  - DOM summary and optional vision understanding
  - structured extraction and human-readable report generation
  - public, login, and first-pass registration-oriented access support

## Confirmed Strengths

- Strong artifact discipline:
  - screenshots
  - DOM snapshots
  - run log
  - page insights
  - extraction outputs
  - readable competitive-analysis reports
- Good fit for evidence-backed analysis because outputs remain inspectable and reproducible.
- Public-site competitive-analysis runs already work on representative targets.
- Multi-site orchestration and comparison reporting now exist in first-pass form.

## Current Runtime Notes

- Playwright remains the browser runtime.
- Browser launch now respects configured headless mode instead of forcing visible mode.
- The engine now includes:
  - goal-aware decision scoring
  - validate-after-action checks
  - lightweight site memory
  - challenge detection and human-assisted pause/resume
  - re-observation after meaningful state changes
- Vision is advisory and grounded by DOM snapshots rather than driving raw selectors directly.
- Public multi-site execution is now materially more usable:
  - batch runs can limit concurrent sites
  - per-site outputs are isolated under batch subdirectories
  - vision requests are throttled with a shared in-process concurrency gate
  - CLI can launch one to three ad-hoc target URLs without writing a dedicated batch YAML first

## Recently Fixed Review Issues

- Nav discovery no longer shuts off completely after the first observed page.
  - Cheap nav discovery still runs on later pages.
  - Only expensive hover-menu discovery is cached by nav signature.
- Deferred-route consumption now normalizes common auth phrases such as:
  - `sign up`
  - `sign-up`
  - `signup`
  - `sign in`
  - `signin`
  - `login`
- Pre-observe overlay handling is now lightweight triage, not unconditional dismissal.
  - High-value auth/onboarding overlays are preserved.
  - Low-value cookie/privacy/newsletter overlays can be dismissed.

## Current Gaps Worth Tracking

- Report wording and acceptance criteria should still be framed more consistently around competitive analysis rather than generic browsing completeness.
- Registration mode has first-pass support, but real external validation is still thinner than public-mode validation.
- Comparison report quality still needs calibration against human-written competitive-analysis memos.
- Screenshot ranking is improved, but human-judged validation is still missing.
- Some mojibake / text cleanup remains in the reporting pipeline.
- The new ad-hoc URL runner is optimized for public sites; auth-heavy or challenge-heavy targets still rely more on explicit config.

## Validation State

- `python -m compileall src` passed after the latest runtime fixes.
- `python -m compileall src` also passed after the headless/concurrency/CLI runner changes.
- No meaningful automated test suite is present in the repository right now.
- Runtime confidence still depends mainly on smoke runs.

## External Reference: `web-access`

- `web-access` is centered on a local CDP proxy that connects to the user's existing Chrome and exposes a small HTTP API for browser actions.
- Key traits observed:
  - CDP proxy + HTTP API surface for `new / navigate / eval / click / clickAt / setFiles / screenshot / close`
  - shared browser instance with tab-level isolation
  - environment bootstrap that auto-detects Chrome remote-debugging and auto-starts the proxy
  - site-pattern matching for reusable per-domain experience files
- Most relevant borrow candidates for this repo:
  - stronger site-pattern / domain-experience layer
  - clearer split between cheap DOM operations and user-gesture-like operations
  - explicit environment/bootstrap diagnostics for browser connectivity
- Less attractive borrow point for now:
  - replacing the current Playwright runtime with a CDP-proxy-first architecture would trade away isolation and reproducibility in exchange for easier access to existing user sessions

## Report Quality Work

- Existing crawl artifacts are already sufficient to improve report quality without changing crawl behavior first.
- The main weakness was interpretation quality, not raw evidence volume.
  - reports over-weighted page-type counts
  - reports mixed target-site analysis with self-referential commentary about this project
  - reports did not state route-family skew clearly enough
- `artificialanalysis.ai` is a strong example:
  - old output classified it as `developer_docs`
  - regenerated output from the same artifacts classifies it as `analysis_portal`
  - regenerated output now explicitly calls out 70% evidence concentration in `models` pages
- Fields that proved useful for better reporting:
  - homepage hero and CTA extraction in `dataset.jsonl`
  - route-family concentration inferred from `inventory.json`
  - captured route examples from `inventory.json` and `sitemap.json`
  - page insights from `output/artifacts/page_insights/`
- Report improvements implemented:
  - explicit product thesis
  - route-family distribution
  - primary public entry points
  - product pillars inferred from repeated extracted text
  - coverage caveats tied to extraction success rate and route-family skew
  - route-family-aware screenshot selection
- Remaining cleanup:
  - lower-level structured evidence samples can still include mojibake/noisy labels even when the readable report filters most of them
