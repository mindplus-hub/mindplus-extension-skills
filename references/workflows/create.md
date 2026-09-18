# Leaf: create a new V2 extension

Load this leaf only for `CREATE_FRESH`.

Before source-dependent writes, complete [Lite source selection](../official-repository-discovery.md). Preserve its comparison/fork evidence and add required `lite_source_selection` to the producer handoff.

Before npm lifecycle scripts or extension loading, inspect install hooks, dependencies and executable code for unexplained dangerous behavior per the security scope in [Basic](../review-basic.md). Reuse this evidence in the later Basic review; do not execute suspicious code merely to test it.

## Required contract

Creation consumes an `extension-spec.json` matching [../contracts/extension-spec.schema.json](../contracts/extension-spec.schema.json). The target must be absent or empty and satisfy [project-naming.md](../project-naming.md) before routing.

If identity, mode, block semantics, dependency versions, supported devices, resource provenance, or required acceptance scope is missing, return `WAITING_USER/BLOCKED` with `INPUT.EXTENSION_SPEC_INCOMPLETE`. Ask only for the missing product decision; discoverable file facts do not require a user form.

The spec is authored for first-time extension developers: ask questions in plain language (what the extension does, which sensor library it wraps, what the blocks should read like), derive every technical value yourself from the embedded corpus, and never expect the user to know device IDs, field names, or Builder internals. Boards are chosen from the [device-ids.json](../switch/device-ids.json) dictionary by board name; supportDevices is optional and a whole-arch extension may omit it (see [conventions.md](../switch/conventions.md)).

## Shared corpus (same bundle conversion uses)

The verified V2 reference bundle under `references/switch/` is the shared corpus for creation and conversion. Do not consult sibling example projects for conventions the corpus already covers; corpus-use boundaries are defined in [conventions.md](../switch/conventions.md).

1. Run `scripts/switch/check_reference_release.py --skill-root <skill_root> --offline` and require a valid bundled reference state.
2. Read [shared-v2-patterns.md](../switch/shared-v2-patterns.md), [config-schema.md](../switch/config-schema.md), and [conventions.md](../switch/conventions.md). For block layout decisions also read [block-organization.md](../switch/block-organization.md).
3. Read only the selected internal mode reference: [upload-mode.md](../switch/upload-mode.md) or [python-block-mode.md](../switch/python-block-mode.md).
4. Map the spec into the shared inventory shape, then select topics through the same selector conversion uses:

```text
python scripts/switch/spec_to_inventory.py --spec <extension-spec.json> --output <run_root>/record/spec-inventory.json
python scripts/switch/select_reference_topics.py --inventory <run_root>/record/spec-inventory.json --reference-state <reference_state> --mode <UPLOAD-or-PYTHON_BLOCK> --output <run_root>/record/reference-selection.json
```

   Require `PASS` from both; the adapter reports missing spec fields instead of inferring them. Load only the returned Topic paths.

If the corpus is unavailable or does not cover a requested feature, first apply the Topic fallback defined in [conventions.md](../switch/conventions.md) and [official-corpus.md](../switch/official-corpus.md) (read-only search of public `MindPlus-Ext2` repositories with provenance); only when that also fails (and no user-supplied reference exists) stop as `REFERENCE.UNSUPPORTED_TOPIC`; do not invent a Builder field or API.

## Workflow

```text
REFINE_SPEC -> PREPARE -> CREATE -> VERIFY -> HANDOFF
```

1. Resolve and normalize the new author per [author-identity.md](../switch/author-identity.md), using the user-supplied name or available account/Git/computer username; do not default to template authors. Leave `identity.compatibility_id` empty unless a legacy compatibility target and its source identity are confirmed; never derive it from the new author/id. Freeze the approved spec and record its SHA-256 before project writes. Use the path recorded by `--extension-spec`, otherwise write `<parent_run_root>/extension-spec.json`; the handoff uses that same fallback. Use the BASIC artifact review profile.
2. Use the latest stable Scaffold Release selected for this run through the embedded `scripts/switch/prepare_builder_scaffold.py` helper.
3. When the environment is available and installation is within the request, attempt at most one `npm install`. Record the attempt before starting. Never use `npm ci` or clone the Builder.
4. Create only the extension files and root README authorized by the spec. When producing the cover, apply [cover-design.md](../switch/cover-design.md). Preserve exact IDs, parameter order/defaults, menu values, generator semantics, resources, dependencies, and board conditions. Organize blocks per [block-organization.md](../switch/block-organization.md) using the spec's `blocks[].submenu` annotations; write `supportDevices`, `sku`, and `supportArch` exactly per [conventions.md](../switch/conventions.md) and [device-ids.json](../switch/device-ids.json) — device IDs outside the dictionary stop the run.
5. Replace the Builder README template with evidence-backed project content per [project-readme.md](../switch/project-readme.md), then run `scripts/switch/check_project_readme.py` and record `readme_check: PASS` or its terminal result.
6. Run `scripts/switch/check_converted_extension.py --project-root <project_root> --inventory <run_root>/record/spec-inventory.json --mode <selected_mode>` plus resource checks, and at most one `npm run build` when installation passed.
7. Write a `CREATED` handoff with `review_status: NOT_RUN`, the frozen spec hash, artifacts, checks, and actual install/build evidence.

Creation includes producer static checks. Record unavailable build as NOT_RUN with its limitation, never PASS. Apply [issue-levels.md](../issue-levels.md) to actual defects. Producer completion proceeds to mandatory Basic; no publication until build, block observations, security review and ZIP size checks pass.
