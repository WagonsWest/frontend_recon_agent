# Frontend Recon Agent

`frontend_recon_agent` is a Playwright-based website exploration agent for UX review.

It drives a real browser, captures evidence while exploring, and turns that evidence into a reviewer-style UX report instead of a bare action transcript.

## What It Does

- Explores public or logged-in product surfaces with a bounded state/depth budget
- Preserves screenshots, DOM snapshots, run logs, inventory, coverage, and page insights
- Uses model-assisted page understanding and next-step ranking
- Keeps a full operation trace and explored site hierarchy
- Generates a UX report grounded in the captured runtime artifacts
- Supports pause-and-resume for manual login, verification, or anti-bot checkpoints
- Supports batch runs that aggregate per-site UX reports

## Core Flow

The runtime is organized around one browser loop:

```text
observe -> rank candidates -> act -> validate -> re-observe
```

The project also keeps a separate evidence pipeline:

```text
capture -> normalize -> persist -> summarize -> report
```

That split is deliberate. The browser agent is responsible for exploration. The reporting layer is responsible for turning captured evidence into a readable UX review.

## Current Architecture

```text
src/
  agent/        runtime loop, state machine, execution, finalization, batch runner
  browser/      Playwright controller and auth/session handling
  observer/     route discovery and candidate extraction
  analyzer/     DOM analysis helpers
  extraction/   structured page evidence extraction
  vision/       page understanding and candidate ranking prompts/client/types
  analysis/     runtime artifacts, UX memo synthesis, UX report rendering
  artifacts/    inventory, sitemap, exploration report, artifact management
  tools/        offline report regeneration
```

## Main Outputs

After a run, outputs are written under the configured `output/` directories.

Typical artifacts are:

- `screenshots/`
- `dom_snapshots/`
- `artifacts/inventory.json`
- `artifacts/sitemap.json`
- `artifacts/coverage.json`
- `artifacts/site_hierarchy.json`
- `artifacts/operation_trace.json`
- `artifacts/run_log.jsonl`
- `artifacts/page_insights/`
- `artifacts/dataset.jsonl`
- `artifacts/dataset_summary.json`
- `artifacts/extraction_failures.json`
- `reports/exploration_report.md`
- `reports/site_hierarchy.md`
- `reports/operation_trace.md`
- `reports/ux_report.md`

For batch runs, each site gets an isolated output root under `output/batch/.../sites/<site>/`, and the batch root contains `batch_summary.json`.

## Installation

Requirements:

- Python 3.11+
- Chromium via Playwright
- Optional `OPENAI_API_KEY` for model-assisted vision and candidate ranking

Setup:

```bash
pip install -r requirements.txt
playwright install chromium
```

## Running The Agent

### Single Config Run

```bash
python -m src.cli --config config/smoke_test_public.yaml --clear
```

### Login-Gated UX Review

```bash
python -m src.cli --config config/smoke_test_ponder_ux.yaml --clear
```

If the product requires manual help during login or verification, keep the visible browser open and continue in the terminal when prompted.

### Direct URL Mode

You can pass one to three URLs directly:

```bash
python -m src.cli https://example.com https://example.org
```

You can also combine direct URLs with a base config:

```bash
python -m src.cli --config config/smoke_test_public.yaml --headless https://example.com
```

### Batch Runs

```bash
python -m src.cli --batch-config config/smoke_test_batch.yaml
```

Batch mode writes per-site UX outputs and records their paths in `batch_summary.json`.

## Config Model

Configuration is loaded from:

1. `config/settings.local.yaml` if present
2. `config/settings.yaml`
3. the file passed via `--config`
4. environment overrides

Environment overrides:

- `MIMIC_USERNAME`
- `MIMIC_PASSWORD`

Important config sections:

- `target`
  - `url`
  - `dashboard_url`
  - `site_pattern`
- `task`
  - goal, keywords, captcha policy, re-observation, human assistance
- `login`
  - mode, credentials, selector overrides, verification selectors
- `budget`
  - `max_states`
  - `max_depth`
  - `retry_limit`
- `exploration`
  - route candidate collection and hover-menu discovery
- `interaction`
  - button, modal, expand, and tab selectors
- `browser`
  - headless, viewport, slow motion
- `vision`
  - provider, model, timeout, artifact directories
- `run`
  - profile and runtime feature toggles
- `output`
  - screenshot, DOM, report, and artifact roots

## Login Modes

Supported `login.mode` values:

- `public`
- `login`
- `register`
- `manual`
- `auto`

Use `manual` when the site needs a real human-assisted login flow and you want the run to continue in the same browser session.

## CLI

```text
python -m src.cli [OPTIONS] [TARGET_URL ...]

Options:
  --config, -c PATH
  --batch-config PATH
  --profile TEXT
  --max-states, -s INTEGER
  --max-depth, -d INTEGER
  --headless
  --clear
```

Rules:

- Use either `--batch-config` or direct target URLs, not both
- Direct URL mode accepts at most three targets
- `--clear` clears the configured output root before the run

## Run Profiles

Available profiles:

- `default`
- `smoke_fast`
- `demo`
- `full`

Typical use:

- `smoke_fast` for quick runtime validation
- `demo` for visible, presentation-friendly runs
- `full` for deeper evidence collection

## UX Reporting

The current reporting path is UX-only.

`ux_report.md` is generated from:

- captured states
- run log
- operation trace
- explored site hierarchy
- screenshots
- page insights
- coverage and extraction artifacts

The report is intended to read like a reviewer memo, not a raw crawler dump.

## Offline Regeneration

You can regenerate the UX report and supporting runtime artifacts from an existing run without rerunning the browser:

```bash
python -m src.tools.regenerate_reports --config config/smoke_test_ponder_ux.yaml
```

This is useful when:

- the captured artifacts are already good
- the report logic changed
- you want to iterate on reporting without paying the runtime cost again

## Example Configs

Useful configs in `config/`:

- `smoke_test_public.yaml`
- `smoke_test_public_fast.yaml`
- `smoke_test_lmarena_demo.yaml`
- `smoke_test_ponder_ux.yaml`
- `smoke_test_ponder_ux_deep.yaml`
- `smoke_test_batch.yaml`

## Practical Workflow

1. Run a target site with a bounded budget.
2. Inspect `reports/ux_report.md`.
3. Use `reports/operation_trace.md` and `reports/site_hierarchy.md` to understand what the agent actually did.
4. Open the linked screenshots and DOM snapshots when you need to verify a specific claim.
5. Regenerate reports offline if you improve the reporting logic.

## Status

This is an actively iterated codebase aimed at evidence-backed UX reconnaissance.

The strongest current claim is:

> It can run a real browser session, preserve a usable evidence trail, and turn that trail into a grounded UX report.
