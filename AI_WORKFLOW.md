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

*(to be filled in as the project progresses)*

## Examples where AI significantly improved productivity or influenced a decision

*(to be filled in as concrete examples come up)*

## Examples where AI-generated output required correction, debugging, refinement, or validation

*(to be filled in as concrete examples come up)*