# AI Workflow Guardrails

Review this document before implementation, debugging, refactoring, migrations, or production fixes in this repository.

## Core Rule

Move fast, but move surgically. Prefer the smallest safe change that solves the measured problem. Avoid broad rewrites, speculative refactors, or unrelated cleanup.

## Repo-Specific Focus

- Keep draft and session commands idempotent.
- Handle duplicate Discord events and retries safely.
- Isolate concurrent draft/session state.
- Prefer queue or event-driven boundaries for slow async work.
- Plan rollback paths before changing draft rules or live command behavior.
- Minimize blast radius around live draft flows.

## Required Before Changing Code

- Identify the specific problem and files likely involved.
- Name the expected impact and rollback path.
- Check whether the change affects public traffic, background jobs, auth, user data, data integrity, or production operations.
- Avoid touching unrelated files.

## Architecture Defaults

- Prefer queue-based async processing over synchronous fan-out.
- Prefer append-only events or buffers over hot-row mutation.
- Prefer current-state projections over live aggregation queries.
- Prefer indexed lookups over raw-table scans.
- Prefer batching over per-item work where load can grow.
- Prefer idempotent and retry-safe jobs.

## Job and Workflow Rules

- Jobs and commands must tolerate duplicate execution.
- Bound concurrency and fan-out.
- Make failures observable with enough context to debug.
- Keep retry behavior explicit and safe.
- Avoid synchronized bursts; use jitter or queueing when scheduling work.

## Change Review Checklist

Before finalizing a change, answer:

1. What problem did this solve?
2. What files changed?
3. What is the blast radius?
4. What could break?
5. How do we roll back?
6. What validation proves the change?
7. Did this add load, coupling, or future migration risk?
8. Did this preserve unrelated behavior?
