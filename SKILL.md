---
name: mindplus-agent-skill
metadata:
  version: "0.1.0"
description: Create or freshly convert Mind+ V2 extensions with basic checks, review existing extensions, and publish authorized projects to Gitee. Use HOST_READY acceptance only when explicitly requested. Does not synchronize V1 into an existing V2 project or perform device acceptance.
---

# MindPlus Agent

Use the smallest workflow matching the request. Default: create/convert with basic checks, then publish only if requested. Do not insert a separate review or Mind+ GUI acceptance into ordinary development or publication.

This directory is self-contained. Internal producer names (`mindplus-switch`, `mindplus-create`, `mindplus-review`, `mindplus-gitee-publish`) are not separately installed skills. For maintenance read [architecture.md](references/architecture.md).

## Route and execute

0. Before routing each new task, run `python scripts/update_skill.py` from this skill directory. Compare installed `VERSION` (currently `v0.1.0`) with stable releases at `https://gitee.com/mind-plus/mindplus-agent-skill/releases/`. Runtime files at root/one child directory select the WB ZIP; deeper runtime directories select the universal ZIP. Install only a newer matching Release package, retaining a backup. On `UPDATED`, reload this directory's `SKILL.md` before continuing. On `SKIPPED`, briefly report the reason and continue with the installed version; never force overwrite local Git changes. Do not repeat the check within the same task or an active run. If the user explicitly requests offline use or a pinned version, skip the check.
1. Read [routing.md](references/routing.md).
2. Run `python scripts/mpa.py start --goals <CONVERT,CREATE,REVIEW,PUBLISH> --project-root <abs> --work-root <abs>` with known source/spec paths and authorizations already supplied by the user's request. Ordinary review uses `BASIC`. Pass `--review-profile HOST_READY` only for explicit full acceptance; it inserts a review even when REVIEW is not listed.
3. Follow `next_command` and load only the selected leaf. Record results with `mpa.py handoff`, advance with `mpa.py transition`, and recover interruptions with `mpa.py resume`. Reusing a run ID must not change its request.

| Workflow | Reference |
| --- | --- |
| CONVERT_FRESH | [switch.md](references/workflows/switch.md) |
| CREATE_FRESH | [create.md](references/workflows/create.md) |
| REVIEW_EXISTING | [review.md](references/workflows/review.md) |
| PUBLISH_GITEE | [gitee-publish.md](references/workflows/gitee-publish.md) |

Creation and conversion already include static checks. Reuse those checks; no independent review is required before publishing. Explicit REVIEW runs use BASIC by default. Direct PUBLISH needs authorization and a current publication snapshot, not a HOST_READY certificate. Optional prior handoffs must still match the current project.

## Boundaries and evidence

- Fresh conversion/creation requires an absent or empty target. Existing-V2 synchronization remains unsupported.
- Keep the pinned Scaffold Release and bounded install/build attempts. Build when the environment is available; report skipped or unavailable build separately from static success. Never call skipped work PASS.
- Review is read-only. Rerun affected checks after correction; changing a handoff is not verification.
- Only explicit HOST_READY acceptance requires build, Mind+ import, block visibility and representative compilation. Host observations need user confirmation. Build or publication success never proves hardware behavior.
- Publication checks authorization, exact staged content, secrets, target repository, fast-forward push and remote-ref equality. It does not repeat semantic review. Missing token returns WAITING_USER before Git/remote activity. Never record credentials.
- Reuse authorization already supplied; creating/converting does not itself authorize publication or device actions.

Before handoff/transition read [handoff.md](references/handoff.md). Use [evidence.md](references/evidence.md) to distinguish BASIC, build and HOST_READY claims. The [registry](references/workflow-registry.json) defines allowed transitions.

## Completion

Report the project, achieved checks, limitations and any performed external actions. Successful runs clean hidden run records unless the user requested `--keep-evidence`. Failed or waiting runs retain recovery evidence. A verified push is repository publication, not Mind+ or device acceptance.
