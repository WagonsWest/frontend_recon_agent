# Frontend Mimic Agent

A budget-aware, policy-driven browser agent for autonomous website exploration, artifact collection, and selective analysis. Optimized for admin dashboards, LIMS, ERP, and SaaS management applications.

The current implementation now also supports optional vision-assisted page understanding, structured extraction for list/detail/form pages, and competitive-analysis artifacts in both JSON and Markdown.

## What It Does

1. **Logs into** a target website using configured credentials
2. **Autonomously explores** the site by detecting navigation menus, action buttons, modals, tabs, and expandable rows
3. **Captures artifacts** — full-page screenshots and DOM snapshots for every state
4. **Scores novelty** — uses DOM structural fingerprinting to avoid redundant analysis of near-duplicate pages
5. **Analyzes** pages locally — detects components, layout patterns, design tokens, and tech stack
6. **Produces structured reports** — inventory, site map, execution log, and exploration summary

## Architecture

```
Reasoning Layer  (Claude/ChatGPT via conversation — reviews artifacts, generates code)
       ↑ handoff
Observation Layer (Python — candidate detection, fingerprinting, novelty scoring)
       ↑ data
Execution Layer   (Playwright — navigate, click, capture)
```

For each route page, the agent:
1. Navigates and captures the page
2. Explores all interactions inline (action dropdowns, dropdown items, add buttons, tabs, expandable rows)
3. Uses novelty scoring to skip duplicate interaction states
4. Moves to the next route

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure
cp config/settings.yaml config/settings.local.yaml
# Edit settings.local.yaml with your target URL and credentials

# Run
python -m src.cli
```

## CLI Options

```
python -m src.cli [OPTIONS]

  --config, -c PATH      Path to config YAML file
  --max-states, -s INT   Override max states budget
  --max-depth, -d INT    Override max exploration depth
  --headless             Run browser in headless mode
  --clear                Clear output before running
```

## Targeting a New Website

1. Copy the template config:
   ```bash
   cp config/settings.yaml config/settings.local.yaml
   ```

2. Edit `config/settings.local.yaml` with your target:

   ```yaml
   # Required — your target site
   target:
     url: "https://your-site.com/login"          # Login page URL
     dashboard_url: "https://your-site.com/home"  # Page after login (or leave empty)

   # Required — your credentials
   login:
     username: "your_username"
     password: "your_password"
   ```

   That's it for most Element Plus / Ant Design / Bootstrap admin sites. The defaults handle the rest.

3. **If the site uses a custom UI framework**, also configure selectors:

   ```yaml
   # Optional — customize for non-standard UI frameworks
   login:
     username_selector: "input#my-username"    # CSS selector for username field
     password_selector: "input#my-password"
     submit_selector: "button#login-btn"

   exploration:
     nav_selectors:                            # How to find sidebar/nav menu items
       - ".my-nav-item a[href]"
       - ".sidebar-link"
     submenu_expand_selectors:                 # How to expand collapsed sub-menus
       - ".my-submenu:not(.open) > .toggle"

   interaction:
     action_button_selectors:                  # Action/operation buttons on table rows
       - "button:has-text('Actions')"
     modal_selectors:                          # How to detect open modals/dialogs
       - ".my-modal:visible"
     modal_close_selectors:                    # How to close modals
       - ".my-modal .close-btn"
   ```

4. Run:
   ```bash
   python -m src.cli
   ```

## Configuration Reference

Edit `config/settings.local.yaml`:

| Section | Key Settings |
|---------|-------------|
| `target` | `url` (login page), `dashboard_url` (page after login) |
| `login` | `username`, `password`, form element selectors |
| `crawl` | `wait_after_navigation`, `wait_for_spa`, `interaction_timeout` |
| `budget` | `max_states` (capture limit), `max_depth`, `retry_limit`, `novelty_threshold` |
| `exploration` | `nav_selectors`, `submenu_expand_selectors`, `skip_patterns`, `destructive_keywords` |
| `interaction` | Selectors for action buttons, modals, dropdowns, tabs, expand rows |
| `browser` | `headless`, `viewport_width/height`, `slow_mo` |
| `vision` | `enabled`, `provider`, `model`, `api_base_url`, `api_key_env`, `timeout_ms` |

## Output

After a run, `output/` contains:

```
output/
├── screenshots/           # Full-page PNGs for every captured state
├── dom_snapshots/          # Rendered HTML for every captured state
├── artifacts/
│   ├── inventory.json      # Page inventory with status, paths, novelty scores
│   ├── sitemap.json        # Traversal graph (nodes, edges, groups)
│   ├── coverage.json       # Per-page coverage (what was explored vs missed)
│   ├── run_log.jsonl       # Step-by-step execution log
│   └── analysis/           # Per-state analysis (components, layout, tokens)
│       ├── state_xxxx.json
│       └── ...
└── reports/
    └── exploration_report.md  # Human-readable exploration summary
```

## Key Features

- **Budget-aware** — stops after `max_states` captures, never runs forever
- **Novelty scoring** — DOM fingerprinting skips near-duplicate pages (e.g., 20 identical table views)
- **Autonomous navigation** — detects sidebar menus, nav items, tabs, action dropdowns automatically
- **Recovery** — retries on failure, re-authenticates on session expiry, backtracks on dead ends
- **Structured logging** — every action is logged with timestamp, duration, result, and reason
- **No API keys needed** — all analysis is local; LLM reasoning happens in your Claude/ChatGPT conversation
- **Framework-agnostic** — configurable selectors support Element Plus, Ant Design, Bootstrap, and custom UIs

## Workflow with Claude/ChatGPT

## Current Extensions

- Optional vision-enhanced page understanding
- Structured extraction for list/detail/form pages
- Dataset artifacts:
  - `dataset.jsonl`
  - `dataset_summary.json`
  - `extraction_failures.json`
- Competitive-analysis outputs:
  - `competitive_analysis.json`
  - `competitive_analysis.md`

Notes:
- DOM-first exploration and local analysis work without API keys
- Vision enhancement requires API credentials because screenshot understanding is provider-backed

The intended workflow:

1. Run the agent: `python -m src.cli`
2. Review `exploration_report.md`, `dataset.jsonl`, and `competitive_analysis.md`
3. Bring the outputs to Claude Code or ChatGPT
4. Ask for a product teardown, frontend rebuild, or benchmark comparison using the generated artifacts

## Requirements

- Python 3.11+
- Playwright + Chromium
- A visitor/test account for the target website
