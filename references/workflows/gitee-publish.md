# Leaf: publish the frozen project to Gitee

Load this leaf only for `PUBLISH_GITEE`.

Publication is transport, not a repair stage. It may create Git metadata, a commit, a remote repository, and a pushed ref only within explicit authorization. It must not edit, generate, reformat, or “complete” project content after review. If content needs changing, refresh affected checks and the publication snapshot before staging. Do not repeat semantic review by default.

## First gate: local token presence

Before reading project paths, the review handoff, Git state, or Gitee API details, run:

```text
python scripts/prepare_gitee_publish.py \
  --project-root <project_root> \
  --auth commit --auth push \
  [--review-handoff <current-handoff.json>] [--require-host-ready] \
  [--create-repo] \
  --output <run-evidence>/publish-preflight.json
```

Use `--create-repo` only for an explicitly requested new repository.

The script's first gate never prints the credential value. On Windows it asks Git Credential Manager for `protocol=https` and `host=gitee.com`; with `credential.helper=manager` or `manager-core`, this reads the password stored under `git:https://gitee.com` in Windows Credential Manager. A non-empty `GITEE_TOKEN` or `GITEE_ACCESS_TOKEN` remains an explicit CI/test override. On non-Windows hosts, a single-line `~/.gitee-token` file is also accepted. If no token is present:

1. Return `WAITING_USER/BLOCKED`, outcome `TOKEN_REQUIRED`, reason `AUTH.GITEE_TOKEN_MISSING`.
2. Tell the user to sign in to Gitee, apply for a personal access token, and save it as the password of the `git:https://gitee.com` Windows Credential Manager entry (or use the documented non-Windows/CI source).
3. Do not read [gitee-api.md](../gitee-api.md), resolve the project/handoff, run Git, inspect remotes, contact Gitee, or create anything.
4. Do not ask the user to paste the token into chat or place it in a command line, URL, handoff, report, remote, or tracked file.
5. Resume only after the user says the token is locally available and the preflight passes.

## Authorization and snapshot gate

After token presence, require explicit commit/push authorization (`--auth commit --auth push`). New-repository mode additionally requires `--auth create_repository` and `--create-repo`. The current route supplies these authorizations; a prior review need not already carry permission for a later publication request.

A review handoff is optional. Without one, preflight snapshots the current project and records authorization. If supplied, producer or review evidence must be passing and its project/hash must match. This run's latest producer/review result takes precedence over older external evidence. With explicit `--require-host-ready`, the HOST_READY outcome and user-confirmed host gates remain mandatory.

No separate static audit, provenance ledger, build or GUI acceptance is added by publication. Plan/commit still inspect the exact file set, staged content, secrets and committed tree. Drift invalidates the publication snapshot; refresh affected checks and preflight rather than automatically demanding full acceptance.

Missing authorization is WAITING_USER. A supplied invalid/stale handoff blocks; do not edit it to manufacture success.

## Freeze the publication target

Resolve the requested repository, branch, remote name and commit message before mutation. Reuse unambiguous facts from the current repository and user request; ask only when the destination/effect is ambiguous. For a new repository, also establish owner, name and intended visibility; public visibility is never assumed. Existing-repository description and visibility are verification facts, not permission to change them.

After the token gate, read [gitee-api.md](../gitee-api.md) and recheck its version-sensitive interface if the remote implementation is being changed. Normal publication should follow that API contract and standard Git operations rather than redesigning authentication in this run.

## Publication evidence plan

Create the publication plan and evidence outside `project_root`, normally under the parent run's `evidence/` directory. Record:

- Publication snapshot hash and source file count.
- Exact staged path list and exclusions.
- Local repository/branch/HEAD/worktree facts.
- Sanitized remote name and URL without credentials.
- Requested owner, repository, visibility, branch, and mode.
- Secret-scan, staged-diff, fast-forward, push, and remote-ref results.

The passing publication handoff must include these required check IDs:

```text
publication_snapshot_current
publication_set_reviewed
git_commit
gitee_repository
remote_ref_verified
```

Every passing check needs non-empty evidence. Never record the token, authorization header, credential-helper payload, or credential-bearing diagnostics.

## Publication stages

The stages below are implemented by the deterministic tool; run them in order and never improvise git commands for them:

```text
python scripts/prepare_gitee_publish.py ... --output <run-evidence>/publish-preflight.json   # first gate (above)
python scripts/gitee_publish.py plan    --preflight <preflight.json> --state-dir <run-evidence>/publish
python scripts/gitee_publish.py commit  --preflight <preflight.json> --state-dir <run-evidence>/publish --message <explicit message> [--branch <b>] [--author-name <n> --author-email <e>]
python scripts/gitee_publish.py remote  --preflight <preflight.json> --state-dir <run-evidence>/publish --owner <o> --repo-name <r> [--org <org>] [--create --private|--public --description <d>] [--remote-name origin] [--ssh]
python scripts/gitee_publish.py push    --preflight <preflight.json> --state-dir <run-evidence>/publish
```

`--ssh` / `--https` pick the git transport explicitly. **Default (neither flag): the tool probes non-interactive SSH first (BatchMode) and uses SSH (`git@gitee.com:...`) when it passes; on probe failure it falls back to HTTPS+token and records `fallback_reason` in the remote record.** With `--ssh` a failed probe stops as `AUTH.SSH_KEY_NOT_USABLE` instead of falling back. HTTPS transport supplies the token resolved in process memory through a generated process-local `GIT_ASKPASS` shim (the shim itself contains no secret). All Gitee API operations (token-account resolution, repository creation/verification, post-push ref verification) always use the token regardless of transport.

The tool enforces the stage rules below and writes `publish-plan.json`, `publish-commit.json`, `publish-remote.json`, `publish-push.json` into the state directory; on `PASS` its output carries the ready-made `mpa.py handoff` command with the five required check IDs pre-filled. The token never enters a URL, command argument, log, or file.

```text
PREPARE -> COMMIT -> ENSURE_REMOTE -> PUSH -> VERIFY
```

### PREPARE

- Use the successful preflight's read-only Git facts.
- Inspect branch, HEAD, index, full worktree status, remotes, and candidate paths. Classify user-owned and unrelated changes; do not stage them.
- Build an explicit file manifest for the frozen project. Never use `git add .`, `git add -A` without path limits, or a wildcard that can absorb unreviewed files.
- Exclude `node_modules`, `build`, caches, `.mindplus-agent`, `.ms`, logs, editor state, generated credentials, and unrelated artifacts. Do not assume `.gitignore` makes the set safe.
- Scan every candidate file and the later staged diff for tokens, passwords, private URLs, certificates/private keys, large accidental archives, and machine-specific paths.
- Recompute the project hash immediately before staging. It must still equal the snapshot hash.
- If `.gitignore`, README, metadata, generated files, or any source content needs changing, stop with `REVIEW.STALE_HOST_READY_HANDOFF` after the user changes it and refresh the affected checks and preflight. Publishing must not make that edit.

A dirty Git worktree is not automatically safe merely because its files were hashed. The publication manifest must show that every staged addition, modification, and deletion belongs to the frozen project and intended repository.

### COMMIT

- If Git is uninitialized, initialize only inside the exact project root and on the explicit branch. `.git` metadata is allowed; no project file may be added or rewritten as part of initialization.
- If author name/email are unavailable, return `WAITING_USER`. Do not invent identity or alter global Git configuration.
- Stage explicit approved paths, including intended deletions, and review `git diff --cached --name-status` plus the full staged diff.
- Run `git diff --cached --check` and repeat the secret scan against the staged content. Whitespace findings are advisory (`whitespace_check: WARN`): reviewed third-party content is published verbatim and must not be reformatted to silence them.
- Recompute the project hash after staging. Staging must not change it.
- If the exact reviewed tree is already represented by the intended existing commit, reuse that commit and do not create an empty one. Otherwise create one commit with the explicit message.
- Record tracked deletions in the plan and stage them explicitly, including deletions already staged by the user. Require the complete index path set to match the manifest, and verify the committed tree equals the approved index tree.
- Record the local commit SHA and verify the committed tree represents the approved publication set. Do not amend, rebase, squash, or create extra commits to conceal an error.

Any staged path outside the manifest, secret-like value, unrelated change, or hash drift stops before commit. Do not unstage or rewrite user-owned work destructively.

### ENSURE_REMOTE

For an existing repository:

- Verify exact owner/name, visibility, access, and sanitized clone URL.
- Inspect remote refs before changing local remote configuration.
- If the named Gitee repository does not exist, or its non-empty history is unrelated to the intended local history, stop. Do not delete, recreate, merge, rebase, or force a match.
- If the explicit local `remote_name` is absent, add it with the verified sanitized clone URL. If it already exists with a different URL, stop unless the user explicitly approves that exact URL change.
- Do not overwrite an existing remote URL unless the user explicitly approves that exact change.

For a new repository:

- Require `--create-repo`, `create_repository: true`, and explicit owner/org, name, description, and visibility.
- Check for a collision before creation. A collision is not permission to reuse or recreate it.
- Gitee refuses empty public repositories (HTTP 422), so a requested-public repository is created private and promoted to public with a PATCH only after the push is verified; a failed publish then never leaves a public repository behind.
- Create exactly one repository through the current Gitee API and verify returned owner/name/visibility. Record the sanitized result even if a later push fails.
- Add the explicit local `remote_name` only after the created repository identity and sanitized clone URL have been verified.
- Do not create a README, license, or `.gitignore` remotely because that introduces unreviewed history/content.

### PUSH

- Use a process-local credential bridge that keeps the token out of remote URLs, command arguments, output, files, and persistent Git configuration. If no safe bridge is available, stop as `AUTH.GIT_CREDENTIAL_BRIDGE_REQUIRED`.
- Fetch or inspect the intended remote ref and prove the push is a fast-forward or the first commit to an empty target.
- Push only the explicit local branch to the explicit remote branch.
- Never use `--force`, `--force-with-lease`, tag push, mirror push, branch deletion, or automatic upstream changes outside the approved plan.
- A non-fast-forward, protected branch, permission error, scope error, or remote mismatch is terminal for this run; report it without rewriting history or retrying with broader permission.

### VERIFY

- Query the exact remote branch/ref after push and verify its commit SHA equals the approved local commit.
- Verify owner/name/visibility still match the requested repository.
- Recompute the local project hash; it must still equal the snapshot hash.
- Record what external actions occurred even when a later stage failed.

If the requested public visibility cannot be confirmed after the push, preserve the verified ref evidence in `publish-push.json` and return `BLOCKED/PUSHED_VISIBILITY_PENDING` with reason `GITEE.VISIBILITY_UPDATE_FAILED`. Do not generate a successful handoff; report that the code was pushed but visibility remains unresolved.

Only verified ref equality may return `TERMINAL/PASS`, outcome `PUSHED`. Repository creation or an HTTP success without the intended pushed ref is not publication success.

## Stop behavior and exclusions

Use a precise namespaced reason, including:

- `INPUT.GITEE_TARGET_REQUIRED` for ambiguous target facts.
- `REVIEW.STALE_HOST_READY_HANDOFF` for any reviewed-content drift.
- `GIT.PUBLICATION_SET_MISMATCH` for staged paths outside the reviewed manifest.
- `SECURITY.CREDENTIAL_MATERIAL_FOUND` for secret-like content.
- `GIT.UNRELATED_CHANGES_PRESENT` when safe staging cannot isolate user-owned work.
- `GIT.REMOTE_MISMATCH` or `GIT.NON_FAST_FORWARD` for incompatible remote state.
- `AUTH.SSH_KEY_NOT_USABLE` when `--ssh` was requested but non-interactive SSH authentication fails (missing/unregistered key or a passphrase-protected key).
- `AUTH.GIT_CREDENTIAL_BRIDGE_REQUIRED` when the token cannot be supplied safely.

Finalize through `scripts/mpa.py handoff`. On `PASS`, attach the sanitized publication plan, staged file manifest, commit evidence, repository evidence, and remote-ref verification. On failure or blocking, report the exact completed external actions and the safest recovery point.

Gitee tags, Release objects, attachments, repository deletion/recreation, force push, automatic merge/rebase, and hardware/device operations remain outside this leaf.
