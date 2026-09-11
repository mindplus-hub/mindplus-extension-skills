# Leaf: read-only review

Load only for `REVIEW_EXISTING`. The request selects `BASIC` (default) or explicitly requested `HOST_READY`. Review never silently fixes the project.

## BASIC: default scope

1. Inspect the project configuration against [config-schema.md](../switch/config-schema.md) and the relevant mode, entry files, resources, locale IDs, dependencies, and obvious unfinished placeholders.
2. Check representative generator mappings and obvious semantic defects against available source/spec evidence. Trace changed or risky behavior when needed; do not require a complete per-field provenance ledger or a user-authored behavior manifest merely to inspect an existing project. State what could not be verified.
3. Reuse current producer/static evidence when source hash, scope, command and relevant environment match. Recheck affected content after changes. Build only when requested or useful and the environment is ready; unavailable build/UI evidence is a limitation, not an automatic BASIC failure.
4. Record three required checks: `config_schema`, `extension_static_integrity`, `source_semantics`, each with concrete evidence. Here `source_semantics` means the stated representative static scope, not exhaustive V1 parity or runtime correctness. P0 defects in the selected scope fail the review. Apply [issue-levels.md](../issue-levels.md): record P1/P2 as separate advisory checks, not as failures of these required gates; wording ambiguity alone does not fail source_semantics.
5. Return a concise finding list with file/location, impact and suggested fix. A separate JSON report or provenance ledger is optional unless requested. Use `REVIEWED_BASIC` for a passing BASIC handoff; report unperformed build, Mind+ and hardware checks as `NOT_RUN`/optional.

A BASIC pass does not claim build success, Mind+ importability, target compilation or device behavior. Do not ask the user to launch Mind+ for this profile.

## HOST_READY: explicit acceptance only

When the user asks for full acceptance or Mind+ usability validation, select `--review-profile HOST_READY` and read [review-host-ready.md](review-host-ready.md). Preserve its strict static scope, build, import, block visibility and representative target compilation requirements. Never downgrade an explicitly requested profile. Reuse unchanged evidence rather than rebuilding or asking for the same observations twice.

## Handoff and recovery

Use `mpa.py handoff` with the actual checks and evidence. Missing information essential to the selected scope is `REVIEW_INCOMPLETE`; actual required defects are `REVIEW_NOT_READY`. After correction, rerun the affected checks before recording a new result. Ordinary publication can run independently without this leaf; an explicitly requested failed review in a combined run still stops that run.
