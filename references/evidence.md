# Evidence and review gates

## Evidence layers

| Layer | Examples | Does not prove |
| --- | --- | --- |
| `STATIC` | schema, source, resources, provenance, semantic matrix | Builder, Mind+, or device behavior |
| `HOST_BUILD` | package build, Mind+ import, blocks visible, representative target compilation | upload or physical behavior |
| `RUNTIME` | generated-code observation, simulator/service behavior | physical device acceptance |
| `EXTERNAL_DEVICE` | verified remote ref, upload, boot, sensor/communication observation | untested boards or scenarios |

Use only `PASS`, `FAIL`, `NOT_RUN`, `ACCEPTED_LIMITATION`, and `CARRIED_RISK` for individual checks. A `PASS` on a required check must carry recorded evidence; the Mind+ host GUI checks additionally require `confirmed_by: "user"` — host observations are confirmed by the user, never self-reported by the agent.

## Profiles

| Profile | Required evidence |
| --- | --- |
| `SOURCE_READY` | static checks and fresh Builder package build |
| `HOST_READY` | SOURCE_READY plus Mind+ import, block visibility, and representative target compilation |
| `DEVICE_READY` | HOST_READY plus explicit upload and physical behavior evidence |

`HOST_READY` is the publication minimum. `DEVICE_READY` is required only for claims about concrete hardware behavior.

## Read-only review

Review records each finding with an ID, severity, location, claim, evidence, impact, and recheck condition. If any HOST_READY requirement is `FAIL` or `NOT_RUN`, return a report and stop. Do not edit the project, install a fix, retry by changing code, or silently lower the publication profile.

After the user edits the project, calculate a new source hash or commit and start a new review. Old review evidence cannot authorize publication of changed content.
