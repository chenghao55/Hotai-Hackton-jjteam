# Shared coding-agent instructions

These instructions apply to every coding agent working in this repository. The root `README.md` is the source of truth for architecture and ownership. `docs/STATUS.md` records the latest confirmed team-level state.

## Before every task

1. Read `README.md`.
2. Read `docs/STATUS.md`.
3. Check the current Git branch.
4. Check `git status` and preserve unrelated working-tree changes.
5. Identify which module owns the requested behavior before editing code.

Inspect the current implementation and tests before relying on an issue description, old checkpoint, or branch summary. If they disagree, use the repository as the source of truth and report the mismatch.

## Module ownership

- **Module A** owns photo storage, photo metadata, and shooting guidance.
- **Module B** owns vehicle-condition AI, `AIFinding`, and orchestration from AI findings to Module D `DetectionInput` values.
- **Module C** is team-defined. Do not assign another module's responsibilities to C without an explicit team decision.
- **Module D** owns the `Case` and `Detection` domain, review, appeal, priority, workflow, and payment rules.
- **Module E** owns FastAPI, HTTP schemas and routes, adapters, application composition, and cross-module integration.
- **UI** owns frontend behavior and user interaction.

Keep domain rules in their owning module. Prefer an adapter in Module E when translating between HTTP and an existing public Python contract.

## Cross-module contract changes

If a task requires changing another module's public contract, stop coding that part and explain:

- the blocking contract;
- why an adapter is insufficient;
- the smallest backward-compatible change;
- the affected tests and callers.

Continue only after that contract change is authorized. Do not broaden the change into a redesign.

## Guardrails

- Do not change a public contract merely to make tests pass.
- Do not fabricate photo IDs, evidence provenance, or placeholder domain values.
- Do not put FastAPI types, HTTP concerns, or `HTTPException` in Module D.
- Do not move review, priority, workflow, or payment rules into Module B or Module E.
- Do not rewrite another owner's module during an unrelated task.
- Do not add a database during the MVP unless the team explicitly requests it.
- Do not treat list order as photo provenance when metadata provides the source of truth.
- Do not create a root `CHECKPOINT.md` for individual work.

## Testing and completion reports

Whenever code changes:

1. Run focused tests for the changed behavior.
2. Run the full pytest suite.
3. Report every file changed.
4. Report all public contract changes, or explicitly state that there were none.
5. Report the complete full-suite result, including failures and warnings.

Do not silently repair unrelated failures. Identify whether a failure was introduced by the task or already existed, then stay within the authorized scope.

## Documentation maintenance

Update `README.md` or `docs/STATUS.md` in the same task whenever any of these change:

- module ownership;
- a public API;
- a request or response schema;
- a data model;
- a cross-module flow;
- project structure;
- the development plan;
- the confirmed full-test checkpoint.

Use `README.md` for durable architecture, ownership, contracts, and setup guidance. Use `docs/STATUS.md` for module completion, integration blockers, team-level next steps, and the last confirmed full-test checkpoint.

Keep branch-specific or individual progress in the pull request description or, when a persistent task note is necessary, under `docs/tasks/<task-name>.md`. Do not present one developer's temporary work as the team's current task.
