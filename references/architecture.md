# Architecture contract

One self-contained skill contains five progressively loaded leaves. The router selects work; the leaves implement domain behavior; scripts enforce routing, handoffs and publication transport. No sibling skills or checkouts are required.

Questions: version check -> relevant reference -> answer. Development: version check -> route -> selected leaf -> [Lite source selection](official-repository-discovery.md) -> production -> [Basic](review-basic.md) -> authorized publication. Existing-project review enters Basic directly; standalone publication also requires Basic.

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
CREATE / CONVERT / UPGRADE -> leaf entry LITE -> producer -> REVIEW_EXISTING (BASIC) -> optional PUBLISH
REVIEW                    -> REVIEW_EXISTING (BASIC)
PUBLISH                   -> REVIEW_EXISTING (BASIC) -> PUBLISH_GITEE
```

Lite is a producer entry phase; Basic is the artifact review profile. Publication depends only on the Basic evidence and publication gates documented here.

A findings-only review is a terminal exception: `REPORTED_FINDINGS` records an audit report and retains evidence, but is allowed only on a review-only route. It cannot transition to publication and never relaxes the Basic evidence gate.

Routing decisions live in `scripts/route_workflow.py`; allowed edges live in `references/workflow-registry.json` and are enforced during transition. `mpa.py` composes route/start/handoff/transition/resume. Default profiles and optional detail live in the relevant leaf references.

记录布局、父子关联与分析顺序见 [run-records.md](run-records.md)。

## Evidence and request identity

- Each run owns one immutable request. Identical start is idempotent; a different request needs a new run ID.
- Basic reuses valid producer evidence; changed source, artifacts or relevant environment require affected checks again.
- This run's producer/review handoff takes precedence over external evidence. Only direct publication uses an optional external handoff.
- Publication requires a current Basic report even without a lifecycle handoff. The preflight and every publishing stage recheck source, ZIP and evidence hashes.
- Creation may refine a spec after routing: use the supplied spec path, otherwise `<parent_run_root>/extension-spec.json`, and freeze it before project writes.
- Source hash, publication manifest, committed tree and verified remote ref are separate facts; none proves Mind+ or physical device behavior.

## Packaging

`scripts/switch/` and `references/switch/` hold the shared producer mechanics and verified corpus. Creation enters through `spec_to_inventory.py`; conversion through `inventory_v1.py`. Both reuse topic selection and static checks. Preserve the selected scaffold, source semantics and mode-specific contracts.

Both package variants contain the complete lifecycle. The versioned `mindplus.review-basic/v1` evidence contract binds the source, artifact and checks for reproducible review and publication.
