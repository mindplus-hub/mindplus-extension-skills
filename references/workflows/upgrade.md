# Leaf: upgrade an existing V2 repository

Load only for `UPGRADE_EXISTING` when the user asks to upgrade, fix, or add features to an existing V2 extension. This modifies the existing implementation; it does not synchronize V1 into V2 or recreate the extension from a scaffold.

## Inspect and establish ownership before code changes

1. Locate the actual extension configuration and entry files, inspect the current branch, remotes, working changes, version fields and repository instructions. Verify that this is V2 using [shared-v2-patterns.md](../switch/shared-v2-patterns.md) and the relevant mode reference. A non-empty directory alone is not proof of V2. Preserve unrelated working changes; do not reset, clean, or overwrite them.
2. Identify the source repository and the user's authenticated account. Git author name/email and collaborator push access do not prove personal ownership. If ownership cannot be established, do read-only analysis and ask for the missing account/source information before changing extension files. A local-only repository with no remote can proceed when the user identifies it as their own; record that basis.
3. For a repository not personally owned by the user (including an organization repository), first run `python scripts/check_gitee_token.py`. Reuse a locally stored personal access token; never ask for it in chat or put it in command arguments, URLs, logs or run records. A missing token produces `WAITING_USER/BLOCKED`, `TOKEN_REQUIRED`, `AUTH.GITEE_TOKEN_MISSING` before fork or code changes. An invalid or insufficient token also blocks the fork; token presence alone is not authentication.
4. Authenticate the account and inspect the source repository through the current official Gitee API. Read [gitee-api.md](../gitee-api.md) and verify the current official fork interface before invoking it. Reuse fork authorization already supplied in the request; otherwise obtain authorization for the concrete source and personal destination before creating the remote fork. Fork authorization does not grant commit, push, PR, or release authorization.
5. Reuse an existing personal fork only after verifying its owner and upstream relationship. A same-name unrelated repository is a collision, not a fork. Otherwise create the fork using the personal token, then verify its returned identity, parent/source and usable clone URL. On timeout, look up the fork before retrying; do not blindly repeat creation or delete collisions. Preserve source visibility and licensing. Record the fork URL even if a later step fails.
6. Work on a branch in that verified fork. Prefer a separate checkout when the supplied checkout belongs to upstream or contains working changes. Keep `upstream` pointing to the source and `origin`/the intended push target pointing to the user's fork; verify fetch and push URLs, including branch push settings. Do not silently discard local changes or automatically push to upstream. For a separate checkout, start a new UPGRADE run with that checkout as `project_root` before editing, because a run's path is immutable. Choose the intended upstream base; do not automatically merge a divergent existing fork.

`mpa.py start` freezes `upgrade-baseline.json` with the original project hash. It is read-only evidence creation, not proof of repository ownership. Never replace this baseline after editing. Record the source commit, old extension version, repository ownership/fork verification and requested functionality in the run evidence before implementation. On resume, reuse that evidence and the baseline.

## Implement the requested upgrade and bump its version

1. Derive a concise change plan from the request and current code: expected block behavior, parameters/defaults, generator output, resources, dependencies, supported devices and compatibility. Ask only for missing product decisions that affect implementation. Read [conventions.md](../switch/conventions.md), the selected [upload](../switch/upload-mode.md) or [Python block](../switch/python-block-mode.md) reference, and only topics needed for the changes. Do not apply fresh-conversion cleanup rules to remove unrelated existing fields.
2. Implement the actual requested functionality across configuration, block definitions, generators, locales, library/runtime code and examples as applicable. Preserve extension identity, existing block IDs and saved-project compatibility unless a breaking change is requested. Keep attribution/license and original authorship when forking. Do not replace the existing Builder scaffold or upgrade unrelated dependencies automatically.
3. Determine the authoritative extension version (normally extension `config.json.version`) and any mirrored release/package metadata. Respect the repository's version convention and a user-specified target if it is newer. Otherwise use a patch bump for compatible fixes, minor for compatible added functionality, and major for incompatible changes under SemVer. Handle pre-release or custom formats using the repository convention; ask when ambiguous. Compare version components, not strings, and never downgrade or reuse the current release version.
4. Update all actual mirrors of the extension version and existing release notes/README with the old-to-new version, feature changes and compatibility impact. A Builder tooling `package.json` may have its own independent version: do not mechanically change it or lockfile dependency versions. Update lockfile root metadata only if it mirrors the extension package. This extension version is independent of the skill's `VERSION`; do not set every upgraded extension to the skill version.

When the requested changes include cover creation or replacement, apply [cover-design.md](../switch/cover-design.md); otherwise preserve the existing cover.

When adding blocks or explicitly reorganizing the palette, use [block-organization.md](../switch/block-organization.md); preserve existing public block interfaces outside the requested change.

## Verify and hand off

Run the relevant config, entry/resource, locale and generator checks against the final source, reusing the BASIC scope described in [review.md](review.md) without inserting a separate review workflow. Use project tests or focused regression examples to verify each changed behavior and representative existing behavior, including parameter order, defaults and generated source. Do not invent a V1 inventory to run the conversion checker. Validate README changes with the existing README checker where applicable.

Use the existing build setup when available and authorized. Keep installation/build attempts bounded as in other producers; record a skipped build as optional `NOT_RUN` with a reason, never PASS. Resolve failures in the required checks. Mind+ GUI and device acceptance are not implicit; explicit HOST_READY requests still use the separate acceptance leaf.

Use `mpa.py handoff --workflow UPGRADE_EXISTING --status PASS --outcome UPGRADED` with these required, evidenced PASS checks:

- `repository_ownership`: authenticated personal ownership or verified personal fork (or the stated local-only ownership basis), source/destination and branch.
- `version_bump`: original and final extension versions, comparison and mirrored files.
- `config_schema`, `extension_static_integrity`, `source_semantics`: final configuration, resources/entries and representative semantics.
- `upgrade_regression`: concrete commands/results or traced input/expected/actual generated-source examples covering changed and retained behavior.

The wizard binds `input_provenance.sha256` to the frozen original hash and `project_sha256` to final content. Include actual evidence files via `--evidence <check_id>=<path>` and any deliverable artifacts. Missing required evidence blocks success. Only a passing upgrade may advance to requested review/publication. For `UPGRADE,PUBLISH`, publish through [gitee-publish.md](gitee-publish.md), verifying the personal fork target again immediately before push. No automatic release/tag/PR creation.

Report implemented features, old/new extension versions, affected files, verification results, limitations, and any fork or authorized publication URL.

Before parent handoff, apply [issue-levels.md](../issue-levels.md). P0 blocks; P1/P2 remain evidenced advisory findings. Preserve raw checker results and separate presentation findings from required functional gates.
