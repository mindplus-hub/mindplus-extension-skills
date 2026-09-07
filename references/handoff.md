# Handoff protocol

Every leaf writes one `handoff.json` matching [contracts/handoff.schema.json](contracts/handoff.schema.json). The router uses this file, not natural-language logs, to decide whether a transition is legal.

## Orthogonal result fields

- `state`: `RUNNING`, `WAITING_USER`, or `TERMINAL`.
- `status`: `NOT_RUN`, `PASS`, `FAIL`, or `BLOCKED`.
- `outcome`: domain result such as `CONVERTED`, `CREATED`, `REVIEWED_HOST_READY`, `PUSHED`, or `TOKEN_REQUIRED`.
- `reason_code`: namespaced recovery reason when the run did not pass.

Do not use legacy `CONVERTED_HANDOFF` or `HANDED_OFF` as the universal state. An adapter may translate those values to the fields above while preserving the original log as evidence.

## Required transition checks

- Producer to review: project exists, producer/static checks are recorded, and provenance is stable.
- Review to publish: producer is `mindplus-review`, status is `PASS`, outcome is `REVIEWED_HOST_READY`, `project_sha256` equals a fresh `hash_project.py` result, and all HOST_READY checks are `PASS`.
- Every passing required check carries non-empty `evidence`; the three Mind+ host GUI checks additionally require `confirmed_by: "user"` (observed in the Mind+ host, not self-reported).
- Publication additionally requires `commit` and `push` authorization in the handoff; `prepare_gitee_publish.py` enforces this after the token gate.

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
