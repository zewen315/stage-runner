# AI Workflow

## What the project does

Stage Runner is a workflow orchestrator for staged Python workloads. A **stage** is a
user-defined Python function; a **resource** is versioned data passed between stages.
Resources are schema-validated before promotion, stages run in dependency order, and a
failed or manually-injected-bad resource triggers rollback to the last known-good version.
Prometheus/Grafana/Alertmanager give visibility into run and rollback history. Full detail
in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

## Why I chose the project

1. Staged, validated pipelines are a pattern I've seen widely used for data pipelines in
   past work — this project is inspired by that experience.
2. It's a chance to practice components that are commonly used across the industry: a
   versioned data store, DAG scheduling, container-based execution, Prometheus/Grafana/
   Alertmanager.
3. It doesn't require deep domain knowledge to build or to explain — unlike a project tied
   to a specific business vertical, the value is legible without extra context.
4. It's easy to demonstrate and directly relevant to SRE work: observability, scalability,
   and reliability (validation gates, rollback, and failure injection) are the core of the
   design, not add-ons.

## AI tools and models used

- **Claude Code**, used as the primary development interface for the whole project
  (architecture discussion, code, tests, and this document).
- **Claude Sonnet 5**, the model backing this session.

## How AI was integrated into my engineering workflow

1. Before any implementation, I used AI as a design and review partner, not a decision-maker.
   Starting from a high-level problem and several candidate architectures, we worked through
   trade-offs (e.g. Kafka vs. Postgres as the source of truth for execution state, where
   resource validation should live, how rollback should interact with workflow-level failure
   policy) and pressure-tested the design against edge cases (scheduler crashes, duplicate
   dispatches, invalid resource versions, retries) until it converged on workflows,
   stage-level executions, and versioned resources. I rejected suggestions that added
   unnecessary complexity and explicitly scoped out production concerns (multi-region
   scheduling, distributed scheduler consensus, advanced cron semantics) — the architecture,
   trade-offs, and final calls stayed mine throughout.
2. Feature work started as a short, high-level ask — often a numbered list of wants in one
   message, not a spec. Claude Code would investigate the current code first, propose a
   concrete design when there was a real tradeoff to make, then implement backend, tests,
   CLI, and web UI together in one pass rather than across separate handoffs.
3. Nothing was considered done because tests passed. Every feature was verified against the
   actual running system before moving on — `docker compose up`, injecting real data through
   the CLI, triggering real runs, and inspecting exact API responses — repeated after every
   schema or UI change, not just once at the end.
4. Tests were written alongside each feature as it was built, not requested separately
   afterward — retry exhaustion, fallback, cancellation races, and similar edge cases got
   covered as part of implementing the behavior itself. Integration and system test layers
   were added later, on top of that existing unit-test discipline, once external requirements
   called for them explicitly.
5. UI/UX problems were worked as a tight loop: point at something concrete that looked or
   behaved wrong, get a fix, rebuild, re-verify against the live app, repeat — closer to
   pairing on a diff in real time than handing off a written spec and reviewing later.
6. Documentation was treated as something to audit and correct, not generate once and leave.
   The README and design doc had drifted from an early planning sketch — describing
   observability tooling that was never built, silent on major features that were — and got
   rewritten against the actual system once most of it existed, not written up front and
   assumed still accurate.

## Examples where AI significantly improved productivity or influenced a decision

**1. Keeping the CLI and web UI in lockstep with the API.** Nearly every feature — stage
retries, `on_failure` overrides, interval-based recurring schedules, cancellation at every
level — needed the same capability exposed three ways: the API, the CLI, and the web UI.
Carrying a feature through all three in one pass, instead of writing the API and coming back
to the clients later, kept the CLI's flags and the web form's fields matching whatever the
API actually accepted rather than drifting from it. The web UI itself — a five-plus-page
operate console: dashboard, workflow/resource lists and detail pages, run/schedule detail, a
DAG structure graph — got built and then refined through several rounds of pointing at a
concrete UI problem and getting it fixed, which is a much faster loop than writing and
re-writing the whole thing solo.

**2. The Scheduler's dispatch loop held up across five feature additions.** The Scheduler has
to get retries, `on_failure`/fallback, cancellation, one-off and recurring (cron and interval)
scheduling, and branching DAGs (fan-out/fan-in) all correct at once, without any of them
interfering with each other. Each of those landed as a small, additive change to the same
loop — re-derive what to dispatch from Postgres every tick — rather than forcing a redesign:
cancellation is a check at the top of the loop, fallback is a resolution step before marking a
run failed, branching falls out for free once dispatch means "every stage whose dependencies
are satisfied" instead of "the next stage in a chain." That the loop's shape never needed to
change across five separate additions, each with its own test coverage, is itself the signal
that the original design was right.

## Examples where AI-generated output required correction, debugging, refinement, or validation

**1. Discarding resources that fail validation.** AI's first proposal was to treat a failed
validation as a rejected upload — if it doesn't pass, don't keep it. I corrected that: an
invalid artifact is still evidence — for debugging why a stage produced garbage, for lineage,
for reproducing the failure later — and discarding it throws that away for no real safety
benefit, since *promotion* (becoming the version a run actually reads by default) is already
the gate that matters. The design was corrected to persist every uploaded version regardless
of outcome, recording why it failed alongside it, and gate only promotion on passing.

**2. A worker that owned whole workflow runs.** AI's first proposal had the worker take a
whole workflow run and step through its stages itself. I pushed back: if the worker owns
multi-stage progression, DAG order ends up living in two places — whatever the worker does
internally, and whatever schedules workflows in the first place — and they can drift out of
sync. I corrected the design so the Runner worker is stage-level only: it executes exactly
one stage per dispatch and has no idea what workflow it belongs to beyond what that one stage
needs to run. All DAG/ordering logic lives in exactly one place, the Scheduler. That
correction is also what made branching (fan-out to several stages at once, fan-in waiting on
several) fall out for free later, with no change to the worker at all.