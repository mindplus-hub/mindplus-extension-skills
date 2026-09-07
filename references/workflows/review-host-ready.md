# Optional HOST_READY acceptance

Load only when the request explicitly selects `HOST_READY`. Ordinary BASIC review does not load this file.

## Non-negotiable boundary

Review is read-only. Do not edit source, generate replacement files, install fixes, change configuration, regenerate assets, stage files, or lower the requested profile. An authorized build may create only ignored build output; if it changes any reviewable source file, stop. Findings go back to the user, who changes the project and starts a new review with a new hash.

A parser success or Builder success is never enough. Strict review must determine whether every required field exists, whether every value is valid for its mode, and whether each non-fixed value is supported by evidence rather than copied from an example or invented by the model.

## Inputs and progressive references

Require:

- Absolute `project_root`.
- Current project hash or commit.
- Producer handoff and V1 inventory/frozen creation spec when available.
- For `EXISTING_V2_UNKNOWN`, a user-approved identity and behavior statement whenever the repository itself cannot prove intent.

Read [evidence.md](../evidence.md), [config-schema.md](../switch/config-schema.md), and the machine profile [config-schema.json](../switch/config-schema.json). Read [config identity](../switch/generated/shared/config-identity.md), then load only the selected mode reference:

- `UPLOAD`: [upload config](../switch/generated/upload/config.md).
- `PYTHON_BLOCK`: [Python-block config](../switch/generated/python/config.md).

Determine the mode from the producer route/spec and the actual extension structure. Do not trust `config.mode` by itself. A conflict between route, files, and config is a blocking finding; do not choose whichever value makes the project pass.

## Freeze the reviewed content

1. Run `python scripts/hash_project.py --project-root <project_root>` before inspection.
2. Record the digest and file count in review evidence.
3. Reject symlinks, junctions, unreadable files, or source changes during review.
4. Run the hash again after static checks, build, and host checks. A changed digest makes the review stale and prevents `REVIEWED_HOST_READY`.

`review-report.source_sha256` is the exact reviewed V2 project hash. In the handoff, preserve upstream V1/spec provenance in `input_provenance.sha256` and put the exact reviewed V2 hash in `project_sha256`.

## Required strict static checks

A passing review handoff must include these required check IDs in addition to the four HOST_READY checks:

```text
config_schema
config_value_provenance
extension_static_integrity
source_semantics
```

Do not mark any of them optional. `ACCEPTED_LIMITATION` or `CARRIED_RISK` cannot sign HOST_READY for identity, config, dependency, support-scope, or generator-semantic uncertainty.

## Strict config audit

Audit exactly `<project_root>/extension/public/config.json`.

### 1. Parse and select the profile

- Require a JSON object and reject duplicate keys at every nesting level; ordinary last-key-wins parsing can hide an invalid file.
- Select `UPLOAD` or `PYTHON_BLOCK` from independent route/spec/file evidence.
- Apply the selected profile's `allowed_fields`, `required_fields`, `types`, `fixed_values`, `non_empty_if_present`, and nested `meta` contract.
- Any missing required field, extra field, forbidden V1 field, wrong type, wrong fixed value, empty required structure, unexpected nested key, or mode/profile mismatch is `config_schema=FAIL`.
- Explicitly reject leaked V1 keys `email`, `license`, `isBoard`, `platform`, and `asset`. A repository `LICENSE` file is separate and is not a config field.

For converted projects with a verified inventory, run the existing deterministic baseline:

```text
python scripts/switch/check_converted_extension.py \
  --project-root <project_root> \
  --inventory <verified-v1-inventory.json> \
  --mode <UPLOAD-or-PYTHON_BLOCK> \
  --output <review-evidence>/conversion-check.json
```

Its `PASS` is necessary but not sufficient: it does not prove the truth of arbitrary metadata, support claims, dependency versions, asset provenance, or user-visible behavior. For created or unknown projects, do not fabricate a V1 inventory merely to run the checker; apply the profile and provenance audit directly.

### 2. Build a field provenance ledger

In `review-report.md`, record one row for every present field and every missing required field:

```text
field | actual value summary | rule | evidence source | verdict | finding id
```

Use only these verdicts:

- `PROVEN`: exact value is supported by V1, frozen spec, current source/resource facts, authoritative mode reference, or an explicit user decision.
- `EMPTY_BY_POLICY`: the schema explicitly permits `""` and no stronger fact exists; record what evidence was searched.
- `UNPROVEN`: no evidence supports the value or claimed scope.
- `CONTRADICTED`: evidence supports a different value.
- `NOT_APPLICABLE`: field is excluded by the selected profile.

Examples, sample repositories, model memory, a plausible-looking value, or “commonly used” settings are not provenance. Any non-empty `UNPROVEN` value makes `config_value_provenance` non-passing. `CONTRADICTED` is a failure. If evidence is simply unavailable, use `NOT_RUN`/`REVIEW_INCOMPLETE` rather than calling the value fabricated without proof.

### 3. Apply semantic checks by field

- `id`: lower-case alphanumeric under the current contract; exact approved V2 identity; consistent with message IDs and extension identity. Normalization must be documented.
- `author` and `compatibilityId`: exact approved identities. `compatibilityId` must preserve the proven legacy/spec identity and lower-case form; never derive it from the cleaned V2 ID. Unknown identity blocks publication.
- `version`: three numeric components and consistent with the frozen source/spec and README. Do not silently upgrade it.
- `name.zh-cn`, `name.en`, `description.zh-cn`, and `description.en`: present, non-empty, semantically accurate, and not placeholder/example text. Translation fluency alone does not prove correctness.
- `cover`: safe relative filename that resolves to the actual `public` asset. Record existence, type, dimensions, and provenance. Treat documented visual dimensions as recommendations unless the active contract makes them mandatory.
- `main`, `mode`, and `isDevice`: exact fixed values for the selected profile and consistent with actual output/entry structure. A board-extension shape outside the supported profiles is unsupported, not something to force into `isDevice: false`.
- `sku`: empty is allowed when genuinely unknown; every non-empty model/SKU and separator must be source- or user-proven.
- `meta.runtimeVersion`: match the minimum Runtime API required by APIs actually used. Empty may be `EMPTY_BY_POLICY` only after checking API usage; an arbitrary high version is also unproven because it reduces compatibility.
- `libraryConfig`: in upload mode, contain only proven global Arduino dependencies with exact names and versions. Libraries copied under `public/libraries/` do not belong in this array. An empty array must agree with the actual code and bundled libraries.
- `supportDevices` and `supportArch`: upload-only, non-empty when present, and backed by exact board/architecture evidence. `supportArch` overrides `supportDevices`; flag an accidental combination or an over-broad value such as `["all"]` when the claimed scope is not proven. One representative compile does not prove every declared board or architecture.
- Python-block mode: reject `libraryConfig`, `supportDevices`, and `supportArch`. Verify `public/requirements.txt` only against the frozen spec or the two authoritative V1 Python dependency sources; imports and README guesses are not dependency evidence.

When current references disagree, record `REFERENCE_CONFLICT` and stop rather than selecting the more convenient rule.

## Whole-project static review

Set `extension_static_integrity` and `source_semantics` from evidence covering:

- Required Builder/`extension` structure, valid entry files, and absence of unfinished scaffold placeholders.
- Block opcodes, function names, parameter keys/order/defaults, menu values, block types, and generator mappings.
- Generated code for representative normal, reporter, conditional, loop/HAT, and nested-string paths that actually exist.
- `en`/`zh-cn` locale parity, every `formatMessage` ID, and absence of raw user-visible fallback text.
- Resource existence, case-sensitive path agreement, actual file type, reuse rights/provenance, and no unrelated or placeholder assets.
- Arduino/Python dependency names, versions, bundled files, and license/provenance; configuration must agree with actual imports/includes.
- README identity, version, support scope, examples, and commands must describe the inspected project without unsupported claims.
- Exact V1/spec behavior parity. For `EXISTING_V2_UNKNOWN`, require a user-approved behavior manifest before `source_semantics` can pass; otherwise record `NOT_RUN`.

A static checker cannot prove legacy behavior, importability, board compilation, upload, or physical hardware.

## Legacy parity and platform-adaptation audit

When a conversion or port derives its intended behavior from a V1 library, do not reduce `source_semantics` to matching filenames, block labels, or API names. Trace the observable behavior from the legacy block package through its generator into the invoked implementation, then compare that path with the V2 source and packaged output.

### Establish evidence precedence

- Primary legacy evidence is the actual block declaration or packaged metadata, its generator, and the library implementation it invokes. A frozen creation spec or user-approved behavior manifest can add explicit intent.
- README text, examples, and source comments are supporting evidence. If they disagree with the executable or packaged path, record `REFERENCE_CONFLICT` rather than choosing the convenient interpretation.
- Use authoritative vendor or target-runtime documentation only for platform facts the legacy source cannot establish, such as ADC range/reference, I/O units, runtime initialization, or transport behavior. Those facts may justify an adaptation; they do not redefine the legacy default behavior.
- Treat newly documented calibration, configuration, or convenience behavior as additive unless the user-approved specification explicitly replaces the legacy path. An additive path must not silently change the unconfigured/default result.

### Build a behavior matrix

Record one row per public block and materially distinct execution path:

```text
block/opcode | inputs/types/defaults/menus | generated call | state/defaults | constants/units/algorithm/timing | V2 behavior | classification | evidence
```

Classify every observed difference as one of:

- `PRESERVED`: the V2 path retains the legacy behavior.
- `REQUIRED_PLATFORM_ADAPTATION`: a verified target-platform difference requires a change while preserving the same physical meaning, units, boundary policy, and default observable result as far as the platform permits.
- `INTENTIONAL_ADDITIVE_BEHAVIOR`: an evidenced opt-in path extends the library without altering the legacy default path.
- `DEFECT`: behavior contradicts the legacy source or approved specification.
- `UNPROVEN`: the evidence is insufficient to decide.

Only the first three classifications may support `source_semantics=PASS`, and each needs cited evidence. Any `DEFECT` fails the check; any required `UNPROVEN` comparison leaves the review incomplete.

### Trace numeric and state semantics

- Compare exact lookup tables, constants, formulas, units, ADC scaling, sample counts, delays, filters, initialization order, invalid-input behavior, and default calibration/configuration values. Do not replace a legacy cast or rounding rule with a plausible approximation.
- Record the exact order of parsing, validation, coercion, clipping, rounding, and indexing. Test both endpoints, values just outside each endpoint, fractional values on both sides of every rounding threshold, zero/negative inputs where reachable, and `NaN`/infinity when the public input path can produce them.
- For mutable calibration or configuration, verify the clean-start/no-configuration path, set-then-read ordering, state key and isolation boundary (for example pin, device, bus, or address), replacement/reset behavior, and restart persistence. A setting for one key must not leak into another unless the approved behavior says it is global.

### Verify the produced package without overstating it

- After the fresh Builder build, record the source identity/version and output package identity/version. For files intended to be copied unchanged, compare hashes or exact content between source and package; for bundled/transpiled code, run focused generator or behavior smoke checks against the packaged entrypoint.
- If different contents reuse the same import/cache identity, record the stale-package selection risk and require project-policy or host evidence before treating the corrected package as the one Mind+ will load.
- Unit tests, syntax checks, generator smokes, source/package parity, and Builder success remain `STATIC` or `HOST_BUILD` evidence. For Python-block ports in particular, they do not prove target-runtime initialization, PinPong/board I/O, or physical sensor behavior; keep those observations in the separate `RUNTIME` and `EXTERNAL_DEVICE` gates defined in [evidence.md](../evidence.md).

## Builder and Mind+ host gates

1. `builder_build` requires a fresh successful package build for the exact frozen source and recorded environment. Reuse producer evidence only when the project hash, command, tool versions, and artifacts remain current. Do not install or repair dependencies during review.
2. `mindplus_import` requires the user to import the reviewed build in Mind+.
3. `blocks_visible` requires the user to confirm block visibility, localization, menus, defaults, and representative generated code in Mind+.
4. `representative_target_compile` requires the user to confirm compilation for the declared representative target and record the board/toolchain scope.

The fixed HOST_READY check IDs are:

```text
builder_build
mindplus_import
blocks_visible
representative_target_compile
```

Each must be `PASS` for `REVIEWED_HOST_READY`. Every passing required check needs non-empty evidence. The three Mind+ host checks additionally require `confirmed_by: "user"`; an agent must not self-report those observations.

## Findings, report, and handoff

Write `review-report.json` matching [review-report.schema.json](../contracts/review-report.schema.json) and a human-readable `review-report.md` containing the config provenance ledger. For every issue record ID, severity, exact file/location or JSON path, failed claim, evidence inspected, actual/expected facts, impact, and recheck condition.

Severity guidance:

- `BLOCKER`: invalid/missing identity, entry, mode, required config, secret exposure, stale hash, or a failure that prevents trustworthy import/publication.
- `MAJOR`: unproven or contradicted metadata/support/dependency claim, semantic loss, missing block/menu/locale/resource, or materially misleading README.
- `MINOR`: verified non-blocking quality or documentation issue.
- `INFO`: confirmed limitation or observation that does not weaken a required claim.

Then finalize through `scripts/mpa.py handoff` rather than hand-writing JSON:

- Any required violation: `TERMINAL/FAIL`, outcome `REVIEW_NOT_READY`.
- Missing provenance, build, or user host evidence: `TERMINAL/BLOCKED` or `WAITING_USER/BLOCKED` as appropriate, outcome `REVIEW_INCOMPLETE`.
- All strict static and HOST_READY requirements pass on the unchanged hash: `TERMINAL/PASS`, outcome `REVIEWED_HOST_READY`.

On failure or incomplete evidence, return the reports and the exact user correction/recheck list, then stop. Do not load the publication leaf and do not fix the project.
