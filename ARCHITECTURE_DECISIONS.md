# Architecture Decisions

This file records the main demo-facing technical decisions for the current phase of
`frontend_recon_agent`. Each decision includes the chosen approach, the rationale,
and why the main alternatives were not selected yet.

## ADR-001: Human-Readable Report Layer

- Status: accepted
- Date: 2026-04-09

### Decision

Add a deterministic human-readable report layer that sits on top of the existing
structured competitive-analysis artifacts and embeds a small set of selected
screenshots.

Current output shape:

- `competitive_analysis_structured.md`
  - compact engineering-facing summary
- `competitive_analysis.md`
  - synthesis-driven markdown when enabled, otherwise structured fallback
- `competitive_analysis_readable.md`
  - new stakeholder-facing report with contextual screenshots

### Rationale

- The repo already preserves good evidence, but the final markdown was still too
  close to an engineering summary.
- Demo success depends on a report that a human reviewer can read end to end
  without inspecting raw logs or JSON.
- A deterministic readable report is safer than making the human-facing deliverable
  fully depend on an LLM synthesis call.
- Screenshot insertion makes the report feel closer to a hand-written competitive
  analysis while keeping every claim traceable to captured evidence.

### Alternatives Considered

#### Alternative A: Keep only the current structured markdown

- Rejected for now because it is readable enough for engineers, but not strong
  enough for stakeholder-facing demo use.

#### Alternative B: Make the LLM synthesis output the only human-facing report

- Rejected for now because:
  - it increases demo fragility
  - it makes screenshot placement harder to control
  - it weakens deterministic grounding

#### Alternative C: Dump many screenshots into an appendix/gallery

- Rejected for now because volume is not the problem.
- The report needs selective images placed near the relevant narrative, not a
  large uncurated image archive.

## ADR-002: Budget Profiles For Validation And Demo

- Status: accepted
- Date: 2026-04-09

### Decision

Treat exploration budgets as tiered profiles rather than one implicit default.

Recommended tiers:

- smoke
  - `max_states`: roughly 6-10
  - purpose: syntax/runtime validation, provider checks, selector sanity
- demo
  - `max_states`: roughly 30-60
  - purpose: stakeholder review, single-target competitive-analysis walkthrough
- benchmark
  - `max_states`: roughly 80-150
  - purpose: deeper comparative runs, stronger coverage, better evidence density

### Rationale

- The recent `max_states=6` run was useful as a smoke test, but it should not be
  treated as representative demo coverage.
- A tiered budget model makes it easier to discuss runtime, evidence quality, and
  acceptance criteria without mixing them together.
- Competitive analysis quality depends on enough route and surface coverage, so
  demo runs need a meaningfully higher budget than provider or regression smoke
  tests.

### Alternatives Considered

#### Alternative A: Use one global default budget for everything

- Rejected for now because it hides the distinction between:
  - "the code still runs"
  - "the demo looks convincing"
  - "the benchmark is reasonably complete"

#### Alternative B: Optimize first, then increase budgets later

- Rejected for now because budget realism is a product requirement, not a final
  polish item.
- The team needs to reason about demo-time runtime now, not only after all
  performance work is done.

## ADR-003: Concurrency Strategy

- Status: accepted
- Date: 2026-04-09

### Decision

Prioritize multi-site concurrency before intra-site concurrency.

Execution strategy:

- near term
  - one site = one main control loop
  - multiple independent sites may run concurrently
- later, if needed
  - add bounded intra-site concurrency only for already-discovered route targets
  - keep auth flows, modal flows, and page-local interactions single-threaded

### Rationale

- Multi-site requests such as "analyze site A and site B" are naturally
  independent and map cleanly to separate engines.
- Existing artifacts are already site-scoped, so combining them later into a
  comparison report is straightforward.
- Intra-site concurrency is much riskier because it complicates:
  - per-site memory
  - budget accounting
  - duplicate suppression
  - reproducibility
  - authenticated session side effects

### Alternatives Considered

#### Alternative A: Parallelize pages within a single site immediately

- Rejected for now because it adds concurrency complexity before the demo has
  stable report quality and access-mode coverage.

#### Alternative B: Keep everything single-threaded forever

- Rejected for now because:
  - multi-site compare requests are an explicit requirement
  - higher demo budgets will otherwise stretch wall-clock time too far

#### Alternative C: Use one shared multi-tab browser swarm per site

- Rejected for now because the current architecture intentionally centers on one
  active page per site run, and the controller closes stray tabs to preserve
  determinism.

## ADR-004: Screenshot Selection Policy

- Status: accepted
- Date: 2026-04-09

### Decision

Select a bounded set of screenshots for the readable report using:

- novelty score
- page-type diversity
- extraction success and evidence density
- high-value page hints
- route-level captures before lower-value interaction captures
- report-oriented viewport captures for most pages, while preserving full-page
  captures as archival evidence

### Rationale

- The project already captures screenshots broadly enough.
- The real need is not more images, but better editorial choice.
- Competitive-analysis reports benefit from a few representative visuals that map
  onto key findings.
- Full-page images remain useful for audit and later review, but they are often
  too tall and visually noisy for inline report reading.
- Viewport-oriented report images usually do a better job of matching the way
  humans illustrate findings in competitive-analysis documents.

### Alternatives Considered

#### Alternative A: Select screenshots only by novelty

- Rejected for now because novelty alone can overvalue visually different but
  analytically weak pages.

#### Alternative B: Select screenshots only by page type

- Rejected for now because it ignores evidence density and may miss the most
  informative capture within a page-type bucket.

#### Alternative C: Insert every captured screenshot into the report

- Rejected for now because it would overwhelm the reader and weaken the report's
  editorial quality.

### Important Constraint

- `novelty` is currently a structural DOM-difference heuristic, not a business
  value score and not a visual-design score.
- It is justified as one input for screenshot selection and capture deduplication.
- It is not justified as the sole ranking signal for report importance.

## ADR-005: Demo-Scoped Access Model

- Status: accepted with follow-up validation required
- Date: 2026-04-09

### Decision

Implement exactly four runtime modes in the access layer:

- `public`
- `login`
- `register`
- `auto`

Within demo scope, the explicitly supported user-facing access paths are:

- no-login public browsing
- existing-account login
- email registration leading into entry

The implementation remains selector-driven and config-driven for now instead of
introducing a heavier planner or provider-specific auth abstraction.

### Rationale

- The latest demo requirement names exactly three access paths, so supporting
  them directly is a clearer product fit than building a broader generic auth
  engine first.
- A selector-driven layer fits the current Playwright-based deterministic runtime
  and keeps access behavior auditable.
- `auto` provides a thin convenience layer for experimentation without changing
  the fact that the supported underlying behaviors remain explicit.
- This approach minimizes new architecture while still covering the demo story.

### Alternatives Considered

#### Alternative A: Keep only public browsing and existing-account login

- Rejected because it would leave the stated email-registration requirement
  unimplemented.

#### Alternative B: Build a generalized onboarding planner before shipping the demo

- Rejected for now because:
  - it would materially increase scope
  - it would be harder to validate quickly
  - the demo requirement is narrower than a generic onboarding agent

#### Alternative C: Hard-code one benchmark site's registration flow

- Rejected because it would overfit the runtime and weaken the claim that the
  project supports a demo-scoped access model rather than a site-specific script.

### Known Weaknesses

- The current registration flow is still selector-driven and assumes a relatively
  standard email-signup form shape.
- It does not yet justify support for:
  - email verification inbox handling
  - CAPTCHA-heavy signup flows
  - multi-step registration wizards with nontrivial branching
- The first local mock was useful as a fixture, but it is not a sufficient
  validation target for claiming registration readiness.

## ADR-008: Manual Verification As The First Verification Provider

- Status: accepted for current demo phase
- Date: 2026-04-09

### Decision

Treat email-verification handling as a separate sub-step of registration and make
manual verification the first supported provider.

Current first-pass behavior:

- submit registration form
- detect likely verification / OTP step
- keep the browser visible
- pause for human assistance
- allow either:
  - terminal code entry so the agent can fill the verification input
  - or manual completion in the visible browser followed by resume

### Rationale

- This closes the most important realism gap between "registration form submit"
  and "actual entry into the product" without prematurely coupling the runtime
  to mailbox automation.
- It is materially safer and easier to validate than reading a personal mailbox.
- It matches the current demo stage: prove real registration continuity first,
  then automate code retrieval later through a dedicated provider layer.

### Alternatives Considered

#### Alternative A: Claim email registration support without handling verification

- Rejected because that would overstate the current product capability.

#### Alternative B: Read the user's personal mailbox directly

- Rejected for now because:
  - security risk is too high
  - mailbox UIs and security checks are unstable automation targets
  - it is not a good foundation for a reusable product capability

#### Alternative C: Build mailbox API / IMAP automation before any manual fallback

- Rejected for now because it would slow down verification of the broader
  registration flow and add significant integration scope.

### Known Weaknesses

- This is still human-assisted, not fully automated verification.
- It depends on a visible browser session and an operator at the terminal.
- It is a first provider, not the final verification architecture.

## ADR-006: Independent Multi-Site Concurrency With Post-Run Comparison

- Status: accepted
- Date: 2026-04-09

### Decision

Implement multi-site competitive-analysis requests as:

- one isolated engine run per site
- concurrent execution when targets are independent
- a separate comparison-report aggregation step after the site runs finish

### Rationale

- This matches the user request shape directly:
  - analyze site A
  - analyze site B
  - then compare them
- The existing artifact model is already site-scoped, so isolated per-site runs
  are a natural fit.
- Failure isolation is materially better than in a shared multi-tab or shared
  stateful swarm model.
- It keeps the comparison layer focused on analysis and report synthesis instead
  of mixing cross-site logic into browser control.

### Alternatives Considered

#### Alternative A: One shared browser process that interleaves multiple sites

- Rejected for now because it complicates:
  - logging
  - artifact ownership
  - failure isolation
  - reproducibility

#### Alternative B: Finish all site runs serially, then compare

- Rejected for now because the user explicitly wants simultaneous execution when
  the sites are independent.

#### Alternative C: Build cross-site comparison directly into the main engine loop

- Rejected for now because comparison is analytically downstream from browsing,
  not a browser-control concern.

### Known Weaknesses

- The current comparison report is still more structured-summary than
  analyst-quality narrative.
- This model is clean for a small number of targets, but if batch sizes grow
  significantly we may need more explicit resource controls around browser
  processes and concurrency caps.

## ADR-007: Runtime Profiles And Timing Summaries

- Status: accepted
- Date: 2026-04-09

### Decision

Make run intent explicit through named profiles and per-run timing summaries.

Current profiles:

- `default`
- `smoke_fast`
- `demo`
- `full`

The runtime should also emit a timing summary artifact so performance discussion
is grounded in measured phase costs rather than guesses.

### Rationale

- The repo had drifted into using one heavy runtime path for very different goals:
  - quick regression checks
  - stakeholder demos
  - deeper analysis
- Profile separation lets us lower cost and latency without pretending that
  smoke coverage equals demo coverage.
- Timing summaries are necessary because "the site is slow" and "our pipeline is
  heavy" are different problems that need different fixes.

### Alternatives Considered

#### Alternative A: Keep one runtime path and change only `max_states`

- Rejected because runtime cost is not driven only by frontier size.
- Features such as extraction, re-observation, report screenshots, and vision
  also materially change wall-clock time.

#### Alternative B: Optimize the code first and postpone profile separation

- Rejected for now because profile confusion was already hurting testing and
  decision-making.

#### Alternative C: Add timing logs only when debugging manually

- Rejected because if timing visibility is optional, performance regressions stay
  anecdotal and are harder to compare run to run.

### Known Weaknesses

- `smoke_fast` is intentionally not representative of report quality, so the
  team must not use it as evidence that demo coverage is good enough.
- The current timing summary is phase-oriented and useful, but not yet rich
  enough to answer every micro-bottleneck question.

## Open Questions And Weakly-Justified Areas

These are the current choices that are practical enough to ship for now, but do
not yet have strong enough evidence to treat as settled architecture.

### 1. Local mock registration as the main validation path

- Current view:
  - useful as a fixture
  - weak as a proof target
- Why the justification is weak:
  - it does not capture real-world signup friction
  - the current environment already showed mismatch between shell reachability
    and browser reachability
- Better next step:
  - validate against a controllable external target with a realistic but stable
    email-signup flow

### 2. Selector-driven registration as the long-term access strategy

- Current view:
  - valid first pass for the demo
- Why the justification is weak:
  - selector layouts vary heavily across products
  - the current model is brittle for multi-step registration and verification
- Better next step:
  - compare selector-driven config against a slightly more semantic form-planning
    layer on 2-3 representative signup targets

### 3. Novelty as part of screenshot ranking

- Current view:
  - justified as a structural dedupe signal
- Why the justification is weak:
  - it does not directly measure analytical importance or visual quality
- Better next step:
  - compare the current heuristic against a small human-judged screenshot set
    for report usefulness

### 4. First-pass comparison report shape

- Current view:
  - valid as a batch proof-of-execution artifact
- Why the justification is weak:
  - it has not yet been compared against how humans actually read and use
    competitive comparison memos
- Better next step:
  - evaluate and revise it using 2-3 real human-written comparison reports as
    reference material
