# Leaf: publish the unchanged reviewed project to Gitee

Load this leaf only for `PUBLISH_GITEE`.

Publication is transport, not a repair stage. It may create Git metadata, a commit, a remote repository, and a pushed ref only within explicit authorization. It must not edit, generate, reformat, or “complete” project content after review. If any project file needs changing, stop, let the user change it, and require a new strict review.

## First gate: local token presence

Before reading project paths, the review handoff, Git state, or Gitee API details, run:

```text
python scripts/prepare_gitee_publish.py \
  --project-root <project_root> \
  --review-handoff <review-handoff.json> \
  [--create-repo] \
  --output <run-evidence>/publish-preflight.json
```

Use `--create-repo` only for an explicitly requested new repository.

The script's first gate checks only for a non-empty `GITEE_TOKEN` or `GITEE_ACCESS_TOKEN` and never prints the value. When neither environment variable is set, a local token file `~/.gitee-token` (a single line containing only the token) is accepted as the same credential. If no token is present:

1. Return `WAITING_USER/BLOCKED`, outcome `TOKEN_REQUIRED`, reason `AUTH.GITEE_TOKEN_MISSING`.
2. Tell the user to sign in to Gitee, apply for a personal access token, and expose it locally through one of those environment variables.
3. Do not read [gitee-api.md](../gitee-api.md), resolve the project/handoff, run Git, inspect remotes, contact Gitee, or create anything.
4. Do not ask the user to paste the token into chat or place it in a command line, URL, handoff, report, remote, or tracked file.
5. Resume only after the user says the token is locally available and the preflight passes.

## Enforced review and authorization gate

After token presence, require the preflight to prove all of the following:

- Incoming workflow is `REVIEW_EXISTING` from `mindplus-review` with `TERMINAL/PASS` and outcome `REVIEWED_HOST_READY`.
- All strict required review checks and the four HOST_READY checks pass with evidence; user-confirmed checks retain `confirmed_by: "user"`.
- Handoff `project_root` equals the requested absolute project.
- A fresh `hash_project.py` digest equals handoff `project_sha256`.
- The handoff carries `commit: true` and `push: true`; new repository mode also carries `create_repository: true`.

The generic handoff validator enforces the fixed HOST_READY IDs and every required check that is present. The publication leaf must additionally require `config_schema`, `config_value_provenance`, `extension_static_integrity`, and `source_semantics` to be present, required, `PASS`, and evidenced. Reject an older handoff that omits any of them; do not treat omission as success.

Missing authorization is `WAITING_USER`. Do not edit the handoff to add permission; restart from an explicitly authorized route request. A stale hash, project mismatch, or invalid HOST_READY handoff is blocking and must return to Review.

## Freeze the publication target

Before mutation, obtain explicit values for:

```text
repository_mode: existing | create
owner_type: personal | organization
owner_or_org
repository_name
visibility
description
branch
remote_name
commit_message
```

Do not infer any value from the local folder, token account, an existing remote, or a previous run. Public visibility is never a default. For an existing repository, description/visibility are verification facts rather than permission to change them.

After the token gate, read [gitee-api.md](../gitee-api.md) and recheck its version-sensitive interface if the remote implementation is being changed. Normal publication should follow that API contract and standard Git operations rather than redesigning authentication in this run.

## Publication evidence plan

Create the publication plan and evidence outside `project_root`, normally under the parent run's `evidence/` directory. Record:

- Reviewed project hash and source file count.
- Exact staged path list and exclusions.
- Local repository/branch/HEAD/worktree facts.
- Sanitized remote name and URL without credentials.
- Requested owner, repository, visibility, branch, and mode.
- Secret-scan, staged-diff, fast-forward, push, and remote-ref results.

The passing publication handoff must include these required check IDs:

```text
review_gate_current
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

`--ssh` / `--https` pick the git transport explicitly. **Default (neither flag): the tool probes non-interactive SSH first (BatchMode) and uses SSH (`git@gitee.com:...`) when it passes; on probe failure it falls back to HTTPS+token and records `fallback_reason` in the remote record.** With `--ssh` a failed probe stops as `AUTH.SSH_KEY_NOT_USABLE` instead of falling back. HTTPS transport supplies the token through a generated process-local `GIT_ASKPASS` shim (written into the state directory, reading `GITEE_TOKEN`/`GITEE_AUTH_USER` from the environment; system credential helpers are reset so no GUI dialog can appear). All Gitee API operations (token-account resolution, repository creation/verification, post-push ref verification) always use the token regardless of transport.

The tool enforces the stage rules below and writes `publish-plan.json`, `publish-commit.json`, `publish-remote.json`, `publish-push.json` into the state directory; on `PASS` its output carries the ready-made `mpa.py handoff` command with the five required check IDs pre-filled. The token never enters a URL, command argument, log, or file.

```text
PREPARE -> COMMIT -> ENSURE_REMOTE -> PUSH -> VERIFY
```

### PREPARE

- Use the successful preflight's read-only Git facts.
- Inspect branch, HEAD, index, full worktree status, remotes, and candidate paths. Classify user-owned and unrelated changes; do not stage them.
- Build an explicit file manifest for the reviewed project. Never use `git add .`, `git add -A` without path limits, or a wildcard that can absorb unreviewed files.
- Exclude `node_modules`, `build`, caches, `.mindplus-agent`, `.ms`, logs, editor state, generated credentials, and unrelated artifacts. Do not assume `.gitignore` makes the set safe.
- Scan every candidate file and the later staged diff for tokens, passwords, private URLs, certificates/private keys, large accidental archives, and machine-specific paths.
- Recompute the project hash immediately before staging. It must still equal the reviewed hash.
- If `.gitignore`, README, metadata, generated files, or any source content needs changing, stop with `REVIEW.STALE_HOST_READY_HANDOFF` after the user changes it and require a new Review. Publishing must not make that edit.

A dirty Git worktree is not automatically safe merely because its files were hashed. The publication manifest must show that every staged addition, modification, and deletion belongs to the reviewed project and intended repository.

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
- Recompute the local project hash; it must still equal the reviewed hash.
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
