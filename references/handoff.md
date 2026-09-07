# Handoff protocol

Every leaf writes one `handoff.json` matching [contracts/handoff.schema.json](contracts/handoff.schema.json). The router uses this file, not natural-language logs, to decide whether a transition is legal.

## Orthogonal result fields

- `state`: `RUNNING`, `WAITING_USER`, or `TERMINAL`.
- `status`: `NOT_RUN`, `PASS`, `FAIL`, or `BLOCKED`.
- `outcome`: domain result such as `CONVERTED`, `CREATED`, `REVIEWED_BASIC`, `REVIEWED_HOST_READY`, `PUSHED`, or `TOKEN_REQUIRED`.
- `reason_code`: namespaced recovery reason when the run did not pass.

Do not use legacy `CONVERTED_HANDOFF` or `HANDED_OFF` as the universal state. An adapter may translate those values to the fields above while preserving the original log as evidence.

## Required transition checks

- Producer to publication or requested review: project exists, selected checks pass and provenance is recorded. No automatic independent review.
- BASIC review returns `REVIEWED_BASIC` with evidenced `config_schema`, `extension_static_integrity`, and representative `source_semantics` checks. No GUI/build requirement.
- Explicit HOST_READY returns `REVIEWED_HOST_READY` and retains all host gates; it cannot be replaced by a BASIC result.
- Before publication, validate the upstream handoff when present and recheck the project hash. Direct publication without a handoff freezes its own current snapshot.
- Publication needs current commit/push authorization; a current request may grant this after an earlier read-only review without rewriting that review. Missing token still blocks before Git/remote activity.
- Passing required checks need evidence; host GUI observations additionally need user confirmation.

`input_provenance.sha256` identifies the V1/spec/upstream source. `project_sha256` identifies the exact V2 project content covered by this handoff; never substitute one for the other.
- Missing Gitee token: state `WAITING_USER`, status `BLOCKED`, outcome `TOKEN_REQUIRED`, reason `AUTH.GITEE_TOKEN_MISSING`, and no Git/remote artifacts.

Validate with:

```text
python scripts/validate_handoff.py --input <handoff.json>
python scripts/validate_handoff.py --input <handoff.json> --require-outcome REVIEWED_HOST_READY --check-artifacts
```

The wizard `scripts/mpa.py handoff` assembles this file from flags and enforces the evidence and user-confirmation rules at write time, refusing to write an invalid handoff; prefer it over hand-writing the JSON.

## Secret boundary

Handoffs may record whether an authorization or credential is present, but never its value. Do not include tokens, passwords, cookies, authorization headers, or URLs containing credentials.
