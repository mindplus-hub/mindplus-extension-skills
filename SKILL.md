---
name: mindplus-extension-skills
metadata:
  version: "0.4.4"
description: Create, upgrade and convert Mind+ extensions across upload, Python, MicroPython (mpy) and realtime modes, with Lite source discovery, Basic review and authorized Gitee publishing.
---

# MindPlus Extension Skills

Create, convert or upgrade an extension, review its artifact, then publish if authorized. Lite selects the development source; Basic checks publication readiness. The five leaves belong to this one self-contained skill. For maintenance read [architecture.md](references/architecture.md).

V2 creation, upgrade and review cover UPLOAD, PYTHON_BLOCK, MICROPYTHON and REALTIME (module/stage). Mode contracts: [upload](references/switch/upload-mode.md), [Python](references/switch/python-block-mode.md), [MicroPython](references/switch/micropython-block-mode.md), [realtime](references/switch/realtime-mode.md). Fresh V1 conversion covers all four registered modes; device extensions are outside producer profiles.

For upload development, keep generated Arduino code concise: consider a bundled `.h/.cpp` library for large or repeated implementation logic, leaving parameter handling and calls in `func.js`. See the [upload code organization guidance](references/switch/upload-mode.md#生成代码体量与本地-c-库).

## Entry and routing

1. Questions use only relevant references and receive a direct answer without updates or a lifecycle run. For project work, check [skill-update.md](references/skill-update.md) once per session; reuse the result across tasks and resumes. Explicit update requests or a user-reported newer release trigger another check. Offline/pinned use and local skill maintenance skip automatic updates. After an actual update, reload this entry only.
2. For project work read [routing.md](references/routing.md). Fresh CREATE/CONVERT uses an absent or empty `ext2-<mode>-<name>` directory per [project-naming.md](references/project-naming.md). Start `scripts/mpa.py` with the known request and existing authorization. Invoke scripts by their documented CLI contracts and use the printed JSON as the result — do not read script sources to understand or verify behavior; `--help`, `reason_code` and `next_command` are the contract.
3. Load only the selected leaf. At CREATE/CONVERT/UPGRADE entry, perform **Lite** [source discovery](references/official-repository-discovery.md) before source-dependent writes. Check the appropriate official JSON and Gitee repositories; within the same mode and type, matching config.author + config.id uses an existing base or authorized fork; an id-only collision adds the author suffix (Chinese in pinyin) to the new folder. A changed base/path requires a new immutable route request.
4. Complete the producer, then **Basic** [pre-publication review](references/review-basic.md). The router also inserts Basic before standalone publication. Reuse current checks; do not repeat builds or observations with unchanged scope and artifacts. Follow `next_command`, `handoff`, `transition` and `resume`.

| Workflow | Reference |
| --- | --- |
| CONVERT_FRESH | [switch.md](references/workflows/switch.md) |
| CREATE_FRESH | [create.md](references/workflows/create.md) |
| UPGRADE_EXISTING | [upgrade.md](references/workflows/upgrade.md) |
| REVIEW_EXISTING | [review.md](references/workflows/review.md) |
| PUBLISH_GITEE | [gitee-publish.md](references/workflows/gitee-publish.md) |

## Minimal execution

- Read the selected leaf and needed references once; revisit only changed material or a concrete unresolved failure. Use existing request/file facts; ask only for missing decisions or authorization.
- Run each required check once at its owning stage. Reuse valid producer evidence in Basic and valid Basic evidence in publication; do not add a parallel manual verification of a successful script result.
- Choose verification by the change: wording, metadata and deterministic edits need only a diff; logic changes use the narrowest relevant existing test or reproduction. Reuse passing checks until their inputs change, and stop once the requirement is verified. No default full suite, all-block combinations, duplicate smoke tests or new tests solely for workflow wiring. Broaden only for shared-core impact, a concrete failure or explicit acceptance criteria. Required Basic gates for publication are unchanged.
- Keep findings-only reviews on the report-first branch in [review.md](references/workflows/review.md); a repository URL alone does not request publication readiness.
- Record actual scope/results once and reference them from required check IDs. Keep required checkpoints, handoffs and integrity gates; do not create extra plans, logs or evidence files just to restate them.


## Boundaries and completion

- Basic requires source/config checks, malicious-code review, successful build, observed block display and representative behavior, and an actual extension ZIP no larger than **5,000,000 bytes**. Missing verification retains the project but blocks publication. See [review-basic.md](references/review-basic.md) for the evidence contract.
- [P0/P1/P2](references/issue-levels.md) classify defects, not review levels. P0 blocks approval and publication, not continued review: complete all reachable checks in the selected scope and report all findings together. P1 is advisory; P2 optional. Authorization, secrets, source integrity, fork ownership, artifact size and required verification remain independent gates.
- Existing V2 feature work uses UPGRADE; fresh conversion never overwrites it. Verify an authorized personal fork before editing a non-owned repository. V1-to-existing-V2 synchronization remains unsupported.
- Review does not modify extension source. Authorized builds and checks may write artifacts and evidence. Source fixes belong to development and require affected checks again. Build/push success does not prove physical device behavior.
- Publishing requires authorization and token presence, then current Basic evidence, exact staged content, secret/target checks, fast-forward push, remote-ref, visibility and Topic verification. Never record credentials. Creating or converting alone does not authorize publication.

Before handoff read [handoff.md](references/handoff.md); claims follow [evidence.md](references/evidence.md). Report achieved checks, P0/P1/P2, missing verification, artifact size and actual external actions. Successful runs other than terminal `REPORTED_FINDINGS` clean hidden records unless `--keep-evidence` is requested; terminal `REPORTED_FINDINGS` retains evidence automatically; failed/waiting runs retain them. Never claim deleted evidence remains available. Cleanup failure is `RECORDS.CLEANUP_INCOMPLETE`.
