# Handoff protocol

Every leaf writes one `handoff.json` matching [contracts/handoff.schema.json](contracts/handoff.schema.json). The router uses this file, not natural-language logs, to decide whether a transition is legal.

## Orthogonal result fields

- `state`: `RUNNING`, `WAITING_USER`, or `TERMINAL`.
- `status`: `NOT_RUN`, `PASS`, `FAIL`, or `BLOCKED`.
- `outcome`: domain result such as `CONVERTED`, `CREATED`, `UPGRADED`, `REVIEWED_BASIC`, `REPORTED_FINDINGS`, `PUSHED`, or `TOKEN_REQUIRED`.
- `reason_code`: namespaced recovery reason when the run did not pass.

Do not use legacy `CONVERTED_HANDOFF` or `HANDED_OFF` as the universal state. An adapter may translate those values to the fields above while preserving the original log as evidence.

## Required transition checks

- Producer to Basic: preserve source provenance and `lite_source_selection`; the router inserts `REVIEW_EXISTING`.
- Basic returns `REVIEWED_BASIC` with all eight required checks from [review-basic.md](review-basic.md), plus exactly one `basic_review` artifact. The validator rechecks its actual source, ZIP and evidence hashes.
- A findings-only review returns terminal/PASS `REPORTED_FINDINGS`: it records the four static gates with actual evidence, defers GUI/package checks as optional `NOT_RUN`, has no `basic_review`, and is valid only when there is no publication successor. `PASS` means the report was delivered; it never authorizes publication. Its terminal transition retains evidence for later current-hash reuse.
- Publication requires current passing Basic evidence, even when preflight is called directly without a lifecycle handoff. Static-only results do not substitute for complete Basic evidence.
- Publication still needs commit/push authorization and token presence before Git/remote activity.
- Required checks need evidence; unperformed build/display/behavior is BLOCKED and retains the project.

`input_provenance.sha256` identifies the V1/spec/upstream source. `project_sha256` identifies the exact V2 project content covered by this handoff; never substitute one for the other.
- Missing Gitee token: state `WAITING_USER`, status `BLOCKED`, outcome `TOKEN_REQUIRED`, reason `AUTH.GITEE_TOKEN_MISSING`, and no Git/remote artifacts.

Validate with:

```text
python scripts/validate_handoff.py --input <handoff.json>
python scripts/validate_handoff.py --input <handoff.json> --require-outcome REVIEWED_BASIC --check-artifacts
```

The wizard `scripts/mpa.py handoff` assembles this file from flags and enforces the evidence and user-confirmation rules at write time, refusing to write an invalid handoff; prefer it over hand-writing the JSON.

## Secret boundary

Handoffs may record whether an authorization or credential is present, but never its value. Do not include tokens, passwords, cookies, authorization headers, or URLs containing credentials.

Apply [issue-levels.md](issue-levels.md) to classify development findings. Check `priority` is optional for backward compatibility. `P0` requires `required: true`; `P1`/`P2` require `required: false`. Keep actual FAIL results and evidence for unresolved advisory findings; do not relabel them PASS. Unperformed verification remains NOT_RUN without a defect priority.
