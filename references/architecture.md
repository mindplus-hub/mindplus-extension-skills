# Architecture contract

One self-contained skill contains four progressively loaded leaves. The router selects work; the leaves implement domain behavior; scripts enforce routing, handoffs and publication transport. No sibling skills or checkouts are required.

## Default lifecycle

```text
CREATE_FRESH  -- basic producer checks --> optional PUBLISH_GITEE
CONVERT_FRESH -- basic producer checks --> optional PUBLISH_GITEE
REVIEW_EXISTING (BASIC)                  --> optional PUBLISH_GITEE
PUBLISH_GITEE                            # standalone is supported
```

Explicit `review_profile: HOST_READY` inserts REVIEW_EXISTING after any producer and before publication. It retains full acceptance gates. Ordinary publication has no mandatory review profile.

Routing decisions live in `scripts/route_workflow.py`; allowed edges live in `references/workflow-registry.json` and are enforced during transition. `mpa.py` composes route/start/handoff/transition/resume. Default profiles and optional detail live in the relevant leaf references.

## Evidence and request identity

- Each run owns one immutable request. Identical start is idempotent; a different request needs a new run ID.
- Producer checks are not repeated as an independent review unless requested. Unchanged evidence may be reused; changed content requires affected checks again.
- This run's producer/review handoff takes precedence over external evidence. Only direct publication uses an optional external handoff.
- Publication without a handoff freezes its own source hash after token/authorization checks. A supplied handoff must be current and passing. Explicit HOST_READY requires a valid HOST_READY result.
- Creation may refine a spec after routing: use the supplied spec path, otherwise `<parent_run_root>/extension-spec.json`, and freeze it before project writes.
- Source hash, publication manifest, committed tree and verified remote ref are separate facts; none proves Mind+ or physical device behavior.

## Packaging

`scripts/switch/` and `references/switch/` hold the shared producer mechanics and verified corpus. Creation enters through `spec_to_inventory.py`; conversion through `inventory_v1.py`. Both reuse topic selection and static checks. Preserve the pinned scaffold, source semantics and mode-specific contracts.

HOST_READY detail is in `references/workflows/review-host-ready.md`, loaded only on request. The package remains standalone; future plugin packaging does not change the workflow contract.
