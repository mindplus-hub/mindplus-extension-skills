# Architecture contract

## Purpose

`mindplus-agent-skill` is one discoverable Skill with an internal router. Its leaf workflows are progressive references, not four entrypoint prompts loaded together. Deterministic scripts own repeatable routing and contract checks; leaf references own domain decisions.

```text
user request
    |
    v
SKILL.md thin router
    |
    +-- mpa.py start --> route_workflow.py + workflow-registry.json --> init_run.py
    |
    +-- exactly one selected leaf reference (delivered as next_command)
    |
    +-- mpa.py handoff (write-time assembly + validation) --> handoff.json + validate_handoff.py
    |
    +-- mpa.py transition (gate checks) / mpa.py resume (position rebuild)
    |
    `-- next leaf only when its gate passes
```

## Supported lifecycle

```text
fresh V1 conversion ----+
                        +--> read-only HOST_READY review --> authorized Gitee publish
fresh specification ----+
```

Standalone review and publication are supported. Publication requires a current `REVIEWED_HOST_READY` handoff even when invoked directly.

There is deliberately no `mindplus-sync`. Existing V2 targets are never passed to fresh conversion or overwritten with a scaffold.

## Responsibility split

| Layer | Owns | Must not own |
| --- | --- | --- |
| Router | intent, path facts, workflow sequence, transition gates | extension code or review fixes |
| Leaf | one domain workflow and its handoff | unrelated lifecycle actions |
| Wizard (`mpa.py`) | composing the scripts into one-command steps, `next_command` text, write-time handoff assembly, run advancement | routing rules or gate semantics of its own |
| Scripts | deterministic routing, run setup, token presence, contract validation | product semantics or authorization decisions |
| Contracts | stable machine fields and enums | credentials or copied source content |
| Shared corpus (`references/switch/`) | generated Wiki facts, curated migration standards, conventions dictionary, device-ID dictionary, organization patterns | per-project product decisions |

`references/switch/` is the shared corpus consumed by both producer leaves despite its historical name: conversion enters it through `inventory_v1.py`, creation through `spec_to_inventory.py`, and both converge on the same `select_reference_topics.py` selection and `check_converted_extension.py` static gates (including the device-ID dictionary).

## Accepted decisions

- `HOST_READY` is the minimum Gitee publication gate.
- Review is always read-only. Findings return to the user for correction and later re-review.
- Publication supports an existing Gitee repository or creating a new one after a local personal token is available.
- Without a detected token, publication performs no Git or remote operation and only returns an application/setup reminder.
- Builder setup is the pinned Scaffold Release plus at most one `npm install`; no fresh clone or `npm ci` fallback.
- Git commit, remote creation, push, tag, release, import, upload, and device actions remain separate authorizations, and those authorizations are enforced by scripts (router gates, publication preflight, handoff validation) rather than by prose alone.
- A passing required check needs recorded evidence; the three Mind+ host GUI checks additionally need `confirmed_by: "user"`, so host observations cannot be self-reported by the agent.
- `mpa.py` is the preferred entry: every subcommand output ends with `next_command`, and handoff JSON is assembled by `mpa.py handoff` instead of hand-written. The raw CLIs remain supported and enforce the same contracts.
- Routing rules exist only as the `route_workflow.py` branch chain; reference documents keep no parallel rule table.
- Real-project conventions (device IDs, SKU format, compatibility IDs, runtime versions) live in the curated dictionary `references/switch/conventions.md` + `device-ids.json`; the static checker rejects device IDs outside the dictionary. The skill assumes no local example projects: corpus gaps fall back first to a read-only, provenance-recorded search of the official `gitee.com/mind-plus` organization (`official-corpus.md` protocol, `fetch_official_reference.py`, C2-official evidence), then to a precise user question.

## Packaging boundary

This directory is the only installation unit. The conversion implementation is embedded under `scripts/switch/` and `references/switch/`; creation reuses those internal resources. No workflow may search for a sibling checkout, another installed MindPlus Skill, or a caller-supplied leaf root.

```text
mindplus-agent-skill/
|-- SKILL.md
|-- scripts/
|   |-- mpa.py                  # wizard entry: start / handoff / transition / resume
|   |-- route_workflow.py, init_run.py, validate_handoff.py,
|   |   hash_project.py, prepare_gitee_publish.py, check_gitee_token.py
|   `-- switch/                 # embedded conversion mechanics
`-- references/
    |-- workflows/switch.md     # progressively loaded conversion procedure
    `-- switch/                 # curated and generated conversion facts
```

The string `mindplus-switch` remains in producer fields for handoff compatibility; it names the internal conversion component and does not create a package dependency. A copy of this directory must continue to route conversion and validate its bundled reference release when no adjacent `mindplus-switch` directory exists.

The Skill can be packaged as a plugin later without changing the workflow contract. Plugin manifest and public distribution are outside the current implementation.
