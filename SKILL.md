---
name: mindplus-extension-skills
metadata:
  version: "0.2.1"
description: Create, upgrade existing, or freshly convert Mind+ V2 extensions with basic checks, review existing extensions, and publish authorized projects to Gitee. Use HOST_READY acceptance only when explicitly requested. Does not synchronize V1 into an existing V2 project or perform device acceptance.
---

# MindPlus Extension Skills

Use the smallest workflow matching the request. Default: create/convert/upgrade with basic checks, then publish only if requested. Do not insert a separate review or Mind+ GUI acceptance into ordinary development or publication.

This directory is self-contained. Internal producer names (`mindplus-switch`, `mindplus-create`, `mindplus-upgrade`, `mindplus-review`, `mindplus-gitee-publish`) are not separately installed skills. For maintenance read [architecture.md](references/architecture.md).

## Route and execute

0. Before routing each new task, run `python <absolute path of this skill directory>/scripts/update_skill.py` from any working directory (always pass the absolute script path; the working directory does not matter and the script never renames the skill directory). Compare installed `VERSION` (see root `VERSION`) with stable releases at `https://gitee.com/mind-plus/mindplus-extension-skills/releases/`. Runtime files at root/one child directory select the WB ZIP; deeper runtime directories select the universal ZIP. Install only a newer matching Release package, retaining one compressed rollback ZIP outside skill discovery directories. Never run the updater from `.mindplus-skill-backups`, a staging directory, or a packaged preview. Use the active skill path reported by the client, not a directory found by broad search. Do not automatically delete historical backups or staging directories. If the user reports a known newer release, add `--refresh` to bypass the one-hour check cache. On success verify the returned `installation_root` is the active skill and `installed_version` matches that directory's `VERSION`; updating another copy is not success. On `UPDATED`, reload this directory's `SKILL.md` before continuing. On `SKIPPED`, briefly report the reason and continue with the installed version; never force overwrite local Git changes. Do not repeat the check within the same task or an active run. If the user explicitly requests offline use or a pinned version, skip the check.
1. Immediately after the version check, follow [official-repository-discovery.md](references/official-repository-discovery.md): check the official `https://gitee.com/mind-plus` organization for repositories mentioned in the active conversation. For a matching development base, show verified candidates and ask whether to fork an existing repository before source-dependent writes; reuse an explicit choice already supplied. Public discovery does not require a token; actual fork development follows the upgrade leaf token/ownership gates.
2. Read [routing.md](references/routing.md).
3. Run `python scripts/mpa.py start --goals <CONVERT,CREATE,UPGRADE,REVIEW,PUBLISH> --project-root <abs> --work-root <abs>` with known source/spec paths and authorizations already supplied by the user's request. Ordinary review uses `BASIC`. Pass `--review-profile HOST_READY` only for explicit full acceptance; it inserts a review even when REVIEW is not listed.
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
- Keep the pinned Scaffold Release and bounded install/build attempts. Build when the environment is available; report skipped or unavailable build separately from static success. Never call skipped work PASS.
- Review is read-only. Rerun affected checks after correction; changing a handoff is not verification.
- Only explicit HOST_READY acceptance requires build, Mind+ import, block visibility and representative compilation. Host observations need user confirmation. Build or publication success never proves hardware behavior.
- Publication checks authorization, exact staged content, secrets, target repository, fast-forward push and remote-ref equality. It does not repeat semantic review. Missing token returns WAITING_USER before Git/remote activity. Never record credentials.
- Reuse authorization already supplied; creating/converting does not itself authorize publication or device actions.

Before handoff/transition read [handoff.md](references/handoff.md). Use [evidence.md](references/evidence.md) to distinguish BASIC, build and HOST_READY claims. The [registry](references/workflow-registry.json) defines allowed transitions.

Publication includes adding and verifying the repository Topic `MindPlus-Ext2` after the branch push and requested visibility succeed, preserving existing Topics. This is not a Git tag or Release. If Topic verification fails, report the verified push separately and resume the publication leaf without claiming full completion.

## Completion

Report the project, achieved checks, limitations and any performed external actions. Successful runs clean hidden run records unless the user requested `--keep-evidence`. Failed or waiting runs retain recovery evidence. A verified push is repository publication, not Mind+ or device acceptance.
