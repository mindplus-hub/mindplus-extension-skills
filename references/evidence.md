# Evidence and profiles

| Profile | Scope |
| --- | --- |
| BASIC | Configuration, references/resources and representative static semantics; no mandatory build or GUI |
| SOURCE_READY | Basic source checks plus successful package build |
| HOST_READY | Explicit full static acceptance, current build, Mind+ import, block visibility and representative target compilation |
| DEVICE_READY | Separate explicit physical validation; outside these lifecycle leaves |

Publication has no minimum review profile. It proves the approved repository content reached the verified remote ref, not Mind+ or hardware usability.

Use STATIC for source checks, HOST_BUILD for build/host observations, RUNTIME for runtime behavior and EXTERNAL_DEVICE for remote/device observations with the actual scope stated. Required PASS needs evidence. Mind+ GUI PASS additionally needs `confirmed_by: "user"`.

Do not repeat checks when their source hash, scope, artifacts and relevant environment remain valid. After a change, rerun affected checks. A missing optional build/GUI observation is NOT_RUN, not a BASIC blocker. Explicit HOST_READY retains all its requirements and cannot be silently downgraded.

Review stays read-only. Report actual defects and essential missing evidence; do not replace verification with editing a handoff.
