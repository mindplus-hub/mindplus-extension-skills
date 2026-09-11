# Routing protocol

Read this file before any leaf reference.

At the beginning of a new task, first follow the version-check step in `SKILL.md`: run `python <absolute skill path>/scripts/update_skill.py` from any working directory, then reload `SKILL.md` if updated. This is a skill-entry step, not a network operation inside the deterministic routing CLI. Continue the installed version if the update is unavailable; keep active runs on their existing version.

After that version step, follow [official-repository-discovery.md](official-repository-discovery.md) to check the official organization for the conversation's relevant repositories and resolve whether to use a matching repository as a fork base. This happens before `mpa.py start`; the router cannot infer a conversation-level source choice or fork authorization. Reuse a source decision already supplied.

## Make a route request

Preferred: the wizard, which routes, opens the parent run, and prints the next command.

```text
python scripts/mpa.py start --goals <CONVERT,CREATE,UPGRADE,REVIEW,PUBLISH> --project-root <abs> --work-root <abs> [--v1-source <abs>] [--extension-spec <abs>] [--review-handoff <abs>] [--review-profile BASIC|HOST_READY] [--auth <name>]... [--run-id <id>]
```

Raw CLI with the same contract (JSON in, JSON out):

```text
python scripts/route_workflow.py --input <route-request.json> --output <route-result.json>
```

Request facts, matching [contracts/route-request.schema.json](contracts/route-request.schema.json):

- `goals`: one or more of `CONVERT`, `CREATE`, `UPGRADE`, `REVIEW`, `PUBLISH`, `SYNC`.
- `paths.v1_source`: required for fresh conversion.
- `paths.project_root`: required for all workflows; for conversion/creation it must be absent or empty and named `ext2-<name>`; apply [project-naming.md](project-naming.md) before freezing the request.
- `paths.extension_spec`: optional at route time. Without it, creation freezes `<parent_run_root>/extension-spec.json` before writing the project.
- `paths.review_handoff`: optional current producer/review evidence for direct publication. It does not remove a requested review or override this run's new handoff.
- `review_profile`: BASIC by default. Explicit HOST_READY inserts full acceptance; ordinary publication never inserts review.
- `authorizations`: booleans describing only actions explicitly requested. Never include a token or other secret; token presence is checked later by the publication leaf.

## Where the selection logic lives

There is exactly one implementation of the routing rules: the branch chain in `scripts/route_workflow.py` over the facts above, backed by [workflow-registry.json](workflow-registry.json). This file deliberately keeps no parallel rule table or goal-to-workflow examples; when prose and script disagree, the script wins. The wizard prints a fix hint (`next_command`) for every blocked reason code, and `ROUTE_FIX` in `scripts/mpa.py` is the authoritative recovery text.

The script checks goals, path existence and emptiness, and the authorization gates. It does not inspect V1 block semantics, load Builder references, validate a review handoff, or access Gitee.

## Reason-code index

Blocked or waiting results carry one of these codes; the wizard prints the recovery text for each.

| reason_code | meaning |
| --- | --- |
| `ROUTE.UNSUPPORTED_EXISTING_V2_SYNC` | `SYNC`, or fresh conversion targeting a non-empty project; no fallback |
| `ROUTE.CONFLICTING_PRODUCERS` | more than one of `CONVERT`, `CREATE`, `UPGRADE` requested |
| `ROUTE.UNKNOWN_GOAL` / `ROUTE.NO_WORKFLOW` | unknown goal value / no workflow matched |
| `AUTH.PUSH_NOT_AUTHORIZED` | `PUBLISH` without `commit`+`push` authorization |
| `AUTH.LOCAL_WRITE_REQUIRED` | `CONVERT`/`CREATE`/`UPGRADE` without `local_write` authorization |
| `INPUT.GOALS_REQUIRED` / `INPUT.PROJECT_ROOT_REQUIRED` / `INPUT.V1_SOURCE_REQUIRED` | missing material input |
| `INPUT.V1_SOURCE_NOT_FOUND` / `INPUT.REVIEW_HANDOFF_NOT_FOUND` | supplied path does not exist |
| `WORKSPACE.PROJECT_ROOT_NOT_DIRECTORY` / `WORKSPACE.TARGET_NOT_EMPTY` / `WORKSPACE.PROJECT_PARENT_NOT_FOUND` / `WORKSPACE.EXISTING_PROJECT_REQUIRED` | unusable project_root facts |
| `WORKSPACE.PROJECT_NAME_PREFIX_REQUIRED` | fresh project directory lacks lowercase `ext2-` or a nonempty suffix; correct the target before starting |
| `INPUT.INVALID_ROUTE_REQUEST` | malformed request (wrong types or unknown fields) |

## Route result

A successful route has `state: RUNNING`, `status: PASS`, an ordered `workflows` array, and matching `leaf_references`. Missing material input uses `WAITING_USER/BLOCKED`. Unsupported or unsafe routing uses `TERMINAL/BLOCKED`.
