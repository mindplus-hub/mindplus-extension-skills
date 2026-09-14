---
name: mindplus-extension-skills
metadata:
  version: "0.3.0"
description: Create, upgrade existing, or freshly convert Mind+ V2 extensions with basic checks, review existing extensions, and publish authorized projects to Gitee. Use HOST_READY acceptance only when explicitly requested. Does not synchronize V1 into an existing V2 project or perform device acceptance.
---

# MindPlus Extension Skills

Use the smallest workflow matching the request. Default: create/convert/upgrade with basic checks, then publish only if requested. Do not insert a separate review or Mind+ GUI acceptance into ordinary development or publication.

This directory is self-contained. Internal producer names (`mindplus-switch`, `mindplus-create`, `mindplus-upgrade`, `mindplus-review`, `mindplus-gitee-publish`) are not separately installed skills. For maintenance read [architecture.md](references/architecture.md).

## Route and execute

0. Before each new task, follow [skill-update.md](references/skill-update.md) to check the active installation and reload this skill after an update. Skip for explicit offline or pinned-version use; do not repeat within an active run.
1. Immediately after the version check, follow [official-repository-discovery.md](references/official-repository-discovery.md): check the official `https://gitee.com/mind-plus` organization for repositories mentioned in the active conversation. For a matching development base, show verified candidates and ask whether to fork an existing repository before source-dependent writes; reuse an explicit choice already supplied. Public discovery does not require a token; actual fork development follows the upgrade leaf token/ownership gates.
2. Read [routing.md](references/routing.md).
3. Before CREATE/CONVERT routing, choose an absent or empty outer project directory named `ext2-<name>` per [project-naming.md](references/project-naming.md). Freeze this path only after applying the naming rule. Run `python scripts/mpa.py start --goals <CONVERT,CREATE,UPGRADE,REVIEW,PUBLISH> --project-root <abs> --work-root <abs>` with known source/spec paths and authorizations already supplied by the user's request. Ordinary review uses `BASIC`. Pass `--review-profile HOST_READY` only for explicit full acceptance; it inserts a review even when REVIEW is not listed.
4. Follow `next_command` and load only the selected leaf. Record results with `mpa.py handoff`, advance with `mpa.py transition`, and recover interruptions with `mpa.py resume`. Reusing a run ID must not change its request.

| Workflow | Reference |
| --- | --- |
| CONVERT_FRESH | [switch.md](references/workflows/switch.md) |
| CREATE_FRESH | [create.md](references/workflows/create.md) |
| UPGRADE_EXISTING | [upgrade.md](references/workflows/upgrade.md) |
| REVIEW_EXISTING | [review.md](references/workflows/review.md) |
| PUBLISH_GITEE | [gitee-publish.md](references/workflows/gitee-publish.md) |

Creation, conversion and upgrade already include static checks. Reuse those checks; no independent review is required before publishing. Explicit REVIEW runs use BASIC by default. Direct PUBLISH needs authorization and a current publication snapshot, not a HOST_READY certificate. Optional prior handoffs must still match the current project.

## Pre-publication issue levels

For producer checks and BASIC review, read [issue-levels.md](references/issue-levels.md). P0 blocks completion/publication; P1 is advisory and P2 optional to fix. Classify by actual impact, preserve raw check evidence, and report unperformed verification separately. Do not add an independent review merely to assign levels. Authorization, secrets, repository target and explicitly requested acceptance remain separate gates.

## Boundaries and evidence

- Fresh conversion/creation requires an absent or empty target. Use UPGRADE for feature changes to existing V2 repositories; V1-to-existing-V2 synchronization remains unsupported. For non-owned repositories, authenticate with a personal token and verify a personal fork before modifying extension files; see the upgrade leaf.
- Keep the latest stable Scaffold Release selected for this run and bounded install/build attempts. Build when the environment is available; report skipped or unavailable build separately from static success. Never call skipped work PASS.
- Review is read-only. Rerun affected checks after correction; changing a handoff is not verification.
- Only explicit HOST_READY acceptance requires build, Mind+ import, block visibility and representative compilation. Host observations need user confirmation. Build or publication success never proves hardware behavior.
- Publication checks authorization, exact staged content, secrets, target repository, fast-forward push and remote-ref equality. It does not repeat semantic review. Missing token returns WAITING_USER before Git/remote activity. Never record credentials.
- Reuse authorization already supplied; creating/converting does not itself authorize publication or device actions.

Before handoff/transition read [handoff.md](references/handoff.md). Use [evidence.md](references/evidence.md) to distinguish BASIC, build and HOST_READY claims. The [registry](references/workflow-registry.json) defines allowed transitions.

Publication includes adding and verifying the repository Topic `MindPlus-Ext2` after the branch push and requested visibility succeed, preserving existing Topics. This is not a Git tag or Release. If Topic verification fails, report the verified push separately and resume the publication leaf without claiming full completion.

## Completion

Report the project, achieved checks, limitations and any performed external actions. Successful runs clean hidden run records unless the user requested `--keep-evidence`. Failed or waiting runs retain recovery evidence. A verified push is repository publication, not Mind+ or device acceptance.
