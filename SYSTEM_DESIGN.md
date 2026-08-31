# Requirements

Stage Runner is a workflow orchestrator for staged Python workloads. Each **stage** is a unit
of work (a Python function) that consumes and produces **resources** — versioned data
artifacts passed between stages. Stage Runner validates every resource against a schema
before it is promoted, executes stages in dependency order, and can roll back to the last
known-good resource version (automatically on failure, or on demand) — with full visibility
into run history via Prometheus/Grafana/Alertmanager.

## Functional

1. Users define stage workloads as Python functions, declaring name, dependencies, and
   input/output resource schemas.
2. Each resource a stage produces is validated against its declared schema before being
   promoted to "current".
3. The scheduler executes stages in dependency order (DAG), running each stage's workload in
   an isolated container.
4. On stage failure (execution error or validation failure), the affected resource is
   automatically rolled back to its last known-good version.
5. Operators can manually trigger rollback of a resource, or manually inject a bad resource
   version to test recovery paths (failure injection).
6. Every run emits metrics (stage duration, pass/fail, rollback events) and can trigger
   alerts on failure/rollback.

## Non-functional

1. **Reproducibility** — the full system (scheduler, resource store, Prometheus, Grafana,
   Alertmanager) runs via `docker compose up` on a clean machine.
2. **Simplicity over completeness** — sequential DAG execution is acceptable; parallel stage
   execution is a stretch goal, not a requirement.
3. **Testability** — core logic (DAG resolution, validation, rollback) is unit-testable
   without Docker; container execution is covered by integration tests.
4. **Auditability** — every resource version and stage run is retained (append-only), so a
   failure or rollback is explainable after the fact.

**Out of scope:** distributed/multi-node scheduling, authn/authz, multi-tenant isolation,
non-Python workloads.

# Core API & Entities

# Components

# Deep Dive

Design decisions