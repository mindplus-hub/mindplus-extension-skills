---
name: mindplus-agent-skill
description: Route and orchestrate Mind+ V2 extension creation, fresh V1-to-V2 conversion, read-only HOST_READY review, and authorized Gitee repository publication through progressive leaf loading and versioned handoffs. Use for one or combined Mind+ extension lifecycle tasks. Do not use for V1-to-existing-V2 synchronization, automatic review fixes, device acceptance, or unrequested Git/Gitee actions.
---

# MindPlus Agent

Route one Mind+ extension lifecycle request through the smallest required set of leaf workflows. Keep the router thin: it selects workflows, validates handoffs, enforces transition gates, and reports progress; it does not implement extension semantics or silently repair review findings.

This Skill is a self-contained distribution unit. Every leaf procedure, script, contract, and reference bundle needed by the four workflows lives inside this directory. Progressive loading controls context only; never resolve a sibling checkout, another installed MindPlus Skill, or a caller-supplied leaf root.

For maintenance of this Skill rather than execution of a lifecycle request, read [references/architecture.md](references/architecture.md). Do not load that design reference during ordinary routing.

## Fixed boundaries

- Supported leaves are `CONVERT_FRESH`, `CREATE_FRESH`, `REVIEW_EXISTING`, and `PUBLISH_GITEE`.
- `mindplus-switch`, `mindplus-create`, `mindplus-review`, and `mindplus-gitee-publish` are internal producer identifiers, not separately installed Skill dependencies.
- There is no sync workflow. A V1 source plus an existing non-empty V2 target is `BLOCKED/ROUTE.UNSUPPORTED_EXISTING_V2_SYNC`; never send it to fresh conversion.
- Conversion and creation may perform producer checks, but only the read-only review leaf can issue `HOST_READY`.
- Gitee publication requires a valid `REVIEWED_HOST_READY` handoff.
- Review findings are reported to the user and stop the pipeline. Do not modify the reviewed project; resume only after the user changes it and a new review is run.
- Missing local Gitee token is `WAITING_USER/AUTH.GITEE_TOKEN_MISSING`. In that state, only explain how to apply for and expose the token locally. Do not inspect Git, initialize a repository, stage, commit, create a remote repository, call Gitee, or push.
- Never store or print tokens, passwords, cookies, credential-bearing URLs, or private authentication data.
- Builder preparation uses the pinned Scaffold Release. A producer may attempt at most one `npm install` and one `npm run build`; never substitute `npm ci` or a fresh Builder clone.
- Build evidence is not Mind+ import, target compilation, upload, or device evidence.

## Route first

1. Read [references/routing.md](references/routing.md).
2. Run `scripts/mpa.py start --goals <CONVERT,CREATE,REVIEW,PUBLISH> --project-root <abs> --work-root <abs> [--v1-source <abs>] [--auth <name>]...` with the paths you already know. It routes the request, opens the parent run, and returns `next_command`. Grant `--auth` flags only for actions the user explicitly requested.
3. Follow `next_command` verbatim: read only the leaf it names, execute the leaf, record its result with `scripts/mpa.py handoff`, advance with `scripts/mpa.py transition`, and after any interruption rebuild position with `scripts/mpa.py resume`. A blocked or waiting result already carries its own fix hint — follow it and stop without loading a leaf. A `handoff` refusal listing `user_checklist` means the Mind+ host observations are still missing: hand the checklist to the user instead of confirming yourself. The raw CLIs (`route_workflow.py`, `init_run.py`, `validate_handoff.py`, `prepare_gitee_publish.py`) enforce the same contracts for direct use.

| Workflow | Read only when selected |
| --- | --- |
| `CONVERT_FRESH` | [references/workflows/switch.md](references/workflows/switch.md) |
| `CREATE_FRESH` | [references/workflows/create.md](references/workflows/create.md) |
| `REVIEW_EXISTING` | [references/workflows/review.md](references/workflows/review.md) |
| `PUBLISH_GITEE` | [references/workflows/gitee-publish.md](references/workflows/gitee-publish.md) |

The machine registry is [references/workflow-registry.json](references/workflow-registry.json). It contains routing and transition facts only; leaf procedures remain in their own references.

## Transition through handoffs

Before the first transition, read [references/handoff.md](references/handoff.md). `scripts/mpa.py transition` validates the current handoff and performs these gate checks before advancing; with the raw CLIs, run `scripts/validate_handoff.py` yourself at every boundary. Never infer the next workflow from prose or a legacy log status.

Allowed transitions:

```text
CONVERT_FRESH -> REVIEW_EXISTING
CREATE_FRESH  -> REVIEW_EXISTING
REVIEW_EXISTING -- REVIEWED_HOST_READY --> PUBLISH_GITEE
```

Direct review and direct publish requests are allowed. Direct publish still requires a fresh, valid `REVIEWED_HOST_READY` handoff for the current project hash or commit. Load the next leaf only after its transition gate passes.

## Evidence and permissions

Read [references/evidence.md](references/evidence.md) when creating or evaluating checks. Keep Static, Host/Build, Runtime, and External/Device evidence separate.

Permission does not expand across leaves. Creating or converting a project does not authorize review UI actions, Git commit, Gitee repository creation, push, release, upload, or hardware operations. Reuse authorization already explicit in the user's request, but stop when the target or effect is materially ambiguous.

Authorization is script-enforced, not prose-enforced: `route_workflow.py` stops a `PUBLISH` route without `commit`+`push` or a producer route without `local_write`; `prepare_gitee_publish.py` re-checks the handoff's authorizations after the token gate; `validate_handoff.py` rejects a passing required check without evidence and a Mind+ host GUI check without `confirmed_by: "user"`. Never edit a handoff to bypass these gates; restart from an authorized request.

## Completion

Return the parent run path, each child handoff, current project root, achieved review profile, performed external actions, and the exact next action. Mark unperformed gates `NOT_RUN`; do not describe them as passed. A missing-token publication run ends in `WAITING_USER`, not success or failure. Run records live in hidden `.mindplus-agent/` and `.ms/` directories; a successful run deletes its records on completion unless `--keep-evidence` was set — pass that flag only when the user explicitly asks to retain them.
