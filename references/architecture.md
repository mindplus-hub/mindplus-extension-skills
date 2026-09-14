# Architecture contract

One self-contained skill contains five progressively loaded leaves. The router selects work; the leaves implement domain behavior; scripts enforce routing, handoffs and publication transport. No sibling skills or checkouts are required.

Entry sequence: skill version check -> [official repository discovery and user source choice](official-repository-discovery.md) -> deterministic routing -> selected leaf. Public discovery reuses the corpus lookup helper but runs before routing, independently of technical-reference fallback.

## Instruction placement and maintenance

Keep instructions ordered by scope, not by when a feature was added:

- `SKILL.md`: capability selection, entry sequence, workflow links and cross-workflow boundaries. Keep feature-specific procedures in references.
- Workflow leaves: state applicability first, then inputs, execution and handoff. Link a shared rule at the step that needs it; do not prepend each new feature above applicability.
- Shared references: keep one authoritative description per subject. Directory naming applies before fresh routing; cover design applies during image work; issue levels govern findings. None implicitly expands another subject's scope.
- Scripts and schemas: enforce machine-checkable contracts. Keep prose aligned with them; do not describe a script gate as merely advisory or use presentation guidance to override authorization, source integrity or config requirements.
- README: summarize supported behavior and releases for users; link details instead of duplicating operational instructions. Preserve its architecture, installation and history sections.

For each addition, identify its scope and authoritative file, link it from the relevant step, and check existing exclusions and shared gates for contradictions. Check reference links and packaged paths after moves. User instructions remain authoritative; newer placement or repeated wording does not increase a rule's authority. Do not edit the verified generated corpus to introduce local policy.

## Default lifecycle

```text
CREATE_FRESH  -- basic producer checks --> optional PUBLISH_GITEE
CONVERT_FRESH -- basic producer checks --> optional PUBLISH_GITEE
UPGRADE_EXISTING -- basic upgrade checks --> optional PUBLISH_GITEE
REVIEW_EXISTING (BASIC)                  --> optional PUBLISH_GITEE
PUBLISH_GITEE                            # standalone is supported
```

Explicit `review_profile: HOST_READY` inserts REVIEW_EXISTING after any producer and before publication. It retains full acceptance gates. Ordinary publication has no mandatory review profile.

Routing decisions live in `scripts/route_workflow.py`; allowed edges live in `references/workflow-registry.json` and are enforced during transition. `mpa.py` composes route/start/handoff/transition/resume. Default profiles and optional detail live in the relevant leaf references.

记录布局、父子关联与分析顺序见 [run-records.md](run-records.md)。

## Evidence and request identity

- Each run owns one immutable request. Identical start is idempotent; a different request needs a new run ID.
- Producer checks are not repeated as an independent review unless requested. Unchanged evidence may be reused; changed content requires affected checks again.
- This run's producer/review handoff takes precedence over external evidence. Only direct publication uses an optional external handoff.
- Publication without a handoff freezes its own source hash after token/authorization checks. A supplied handoff must be current and passing. Explicit HOST_READY requires a valid HOST_READY result.
- Creation may refine a spec after routing: use the supplied spec path, otherwise `<parent_run_root>/extension-spec.json`, and freeze it before project writes.
- Source hash, publication manifest, committed tree and verified remote ref are separate facts; none proves Mind+ or physical device behavior.

## Packaging

`scripts/switch/` and `references/switch/` hold the shared producer mechanics and verified corpus. Creation enters through `spec_to_inventory.py`; conversion through `inventory_v1.py`. Both reuse topic selection and static checks. Preserve the selected scaffold, source semantics and mode-specific contracts.

HOST_READY detail is in `references/workflows/review-host-ready.md`, loaded only on request. The package remains standalone; future plugin packaging does not change the workflow contract.
