---
name: mindplus-extension-skills
metadata:
  version: "0.3.6"
description: Create, upgrade or freshly convert Mind+ V2 extensions, check existing sources with Lite duplicate discovery, perform Basic pre-publication review, and publish authorized projects to Gitee.
---

# MindPlus Extension Skills

Create, convert or upgrade an extension, review its artifact, then publish if authorized. Lite selects the development source; Basic checks publication readiness. The five leaves belong to this one self-contained skill. For maintenance read [architecture.md](references/architecture.md).

## Entry and routing

1. Every new task, including a simple question, starts with [skill-update.md](references/skill-update.md). Reuse the completed check within the active task; retain explicit offline/pinned exceptions. After updating, reload this entry. Questions then use only relevant references and receive a direct answer without a lifecycle run.
2. For project work read [routing.md](references/routing.md). Fresh CREATE/CONVERT uses an absent or empty `ext2-<mode>-<name>` directory per [project-naming.md](references/project-naming.md). Start `scripts/mpa.py` with the known request and existing authorization.
3. Load only the selected leaf. At CREATE/CONVERT/UPGRADE entry, perform **Lite** [source discovery](references/official-repository-discovery.md) before source-dependent writes. Check the appropriate official JSON and Gitee repositories; within the same mode and type, matching config.author + config.id uses an existing base or authorized fork; an id-only collision adds the author suffix (Chinese in pinyin) to the new folder. A changed base/path requires a new immutable route request.
4. Complete the producer, then **Basic** [pre-publication review](references/review-basic.md). The router also inserts Basic before standalone publication. Reuse current checks; do not repeat builds or observations with unchanged scope and artifacts. Follow `next_command`, `handoff`, `transition` and `resume`.

| Workflow | Reference |
| --- | --- |
| CONVERT_FRESH | [switch.md](references/workflows/switch.md) |
| CREATE_FRESH | [create.md](references/workflows/create.md) |
| UPGRADE_EXISTING | [upgrade.md](references/workflows/upgrade.md) |
| REVIEW_EXISTING | [review.md](references/workflows/review.md) |
| PUBLISH_GITEE | [gitee-publish.md](references/workflows/gitee-publish.md) |

## Boundaries and completion

- Basic requires source/config checks, malicious-code review, successful build, observed block display and representative behavior, and an actual extension ZIP no larger than **5,000,000 bytes**. Missing verification retains the project but blocks publication. See [review-basic.md](references/review-basic.md) for the evidence contract.
- [P0/P1/P2](references/issue-levels.md) classify defects, not review levels. P0 blocks; P1 is advisory; P2 optional. Authorization, secrets, source integrity, fork ownership, artifact size and required verification remain independent gates.
- Existing V2 feature work uses UPGRADE; fresh conversion never overwrites it. Verify an authorized personal fork before editing a non-owned repository. V1-to-existing-V2 synchronization remains unsupported.
- Review does not modify extension source. Authorized builds and checks may write artifacts and evidence. Source fixes belong to development and require affected checks again. Build/push success does not prove physical device behavior.
- Publishing requires authorization and token presence, then current Basic evidence, exact staged content, secret/target checks, fast-forward push, remote-ref, visibility and Topic verification. Never record credentials. Creating or converting alone does not authorize publication.

Before handoff read [handoff.md](references/handoff.md); claims follow [evidence.md](references/evidence.md). Report achieved checks, P0/P1/P2, missing verification, artifact size and actual external actions. Successful runs clean hidden records unless `--keep-evidence` is requested; failed/waiting runs retain them. Never claim deleted evidence remains available. Cleanup failure is `RECORDS.CLEANUP_INCOMPLETE`.
