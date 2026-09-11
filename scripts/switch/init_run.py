#!/usr/bin/env python3
"""Create one MindPlus-Switch record directory and its checkpoint log."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def inside(child: Path, parent: Path) -> bool:
    """Return whether child is parent or below parent."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def error(message: str, code: int = 2) -> int:
    print(json.dumps({"status": "BLOCKED", "reason_code": "WORKSPACE", "error": message}, ensure_ascii=False))
    return code


def build_log(
    run_id: str,
    source: Path,
    work_root: Path,
    run_root: Path,
    project_root: str,
    mode: str,
    policy: str,
) -> str:
    return f"""# MindPlus-Switch Run Log

- run_id: {run_id}
- v1_source: {source}
- work_root: {work_root}
- run_root: {run_root}
- project_root: {project_root}
- extension_root: NOT_CREATED
- status: RUNNING
- current_step: S-1 OPEN_RUN_LOG
- mode: {mode}
- review_policy: {policy}
- reference_status: NOT_RUN
- reference_release: NOT_RUN
- reference_root: NOT_RUN
- reference_selection: NOT_RUN
- install_attempt: 0
- build_attempt: 0
- install_status: NOT_RUN
- install_exit: NOT_RUN
- install_stall: NONE
- build_status: NOT_RUN
- build_exit: NOT_RUN
- build_stall: NONE
- user_action_required: NONE
- next_workflow: NOT_RUN
- review_status: NOT_RUN
- identity_mapping: NOT_RUN
- compatibility_id: NOT_RUN
- conversion_check: NOT_RUN
- copy_check: NOT_RUN
- readme_check: NOT_RUN

## Checkpoints

- [x] S-1 OPEN_RUN_LOG
- [ ] S0 CHECK_REFERENCE_RELEASE
- [ ] S1 ROUTE
- [ ] S2 LOAD_REFERENCES
- [ ] S3 PREPARE_PROJECT_ROOT
- [ ] S4 NPM_INSTALL
- [ ] S5 VERIFY_V1_SNAPSHOT
- [ ] S6 SEMANTIC_MATRIX
- [ ] S7 IMPLEMENT_EXTENSION
- [ ] S8 UPDATE_README
- [ ] S9 STATIC_CONVERSION_CHECKS
- [ ] S10 BUILD_ONCE
- [ ] S11 HANDOFF

## Route Evidence

- candidates: NOT_RUN
- selected: NONE
- source_anomalies: NOT_RUN
- intervention: NONE

## V1 Snapshot Evidence

- initial_inventory: NOT_RUN
- pre_conversion_inventory: NOT_RUN
- snapshot_compare: NOT_RUN
- snapshot_match: NOT_RUN

## Reference Evidence

- status: NOT_RUN
- release_id: NOT_RUN
- content_sha256: NOT_RUN
- supported_modes: NOT_RUN
- active_root: NOT_RUN
- selection_file: NOT_RUN
- topics_loaded: NOT_RUN

## Builder Evidence

- scaffold_release: NOT_RUN
- scaffold_url: NOT_RUN
- scaffold_sha256: NOT_RUN
- inherited_git: NOT_RUN
- examples_present: NOT_RUN
- node_version: NOT_RUN
- npm_version: NOT_RUN
- npm_install_exit: NOT_RUN
- package_lock_change: NOT_RUN

## Decisions and Risks

- S-1: run records created under .ms; the final project remains outside .ms.

## Event Log

- [{datetime.now(timezone.utc).isoformat()}] [S-1] created run log
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--v1-source", required=True, type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--mode", default="UNKNOWN", choices=["UNKNOWN", "UPLOAD", "PYTHON_BLOCK"])
    parser.add_argument("--review-policy", default="AUTO", choices=["AUTO", "SENSITIVE_REVIEW"])
    args = parser.parse_args()

    for label, value in (("work_root", args.work_root), ("v1_source", args.v1_source)):
        if not value.expanduser().is_absolute():
            return error(f"{label} must be an absolute path: {value}")
    if args.project_root is not None and not args.project_root.expanduser().is_absolute():
        return error(f"project_root must be an absolute path: {args.project_root}")

    work_root = args.work_root.expanduser().resolve()
    source = args.v1_source.expanduser().resolve()
    project_root = args.project_root.expanduser().resolve() if args.project_root is not None else None
    if not work_root.is_dir():
        return error(f"work_root does not exist or is not a directory: {work_root}")
    if not source.is_dir():
        return error(f"v1_source does not exist or is not a directory: {source}")

    ms_root = work_root / ".ms"
    if inside(ms_root, source):
        return error(".ms would be created inside v1_source; choose a separate work_root")
    if project_root is not None:
        if not project_root.name.startswith("ext2-") or not project_root.name[5:].strip():
            return error("fresh project_root must be named ext2-<name>")
        if inside(project_root, source) or inside(source, project_root):
            return error("project_root and v1_source must be separate directory trees")
        if inside(project_root, ms_root) or inside(ms_root, project_root):
            return error("project_root and .ms must be separate directory trees")

    try:
        ms_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return error(f"cannot create .ms directory: {exc}")

    # .ms stores conversion records only; hide it on Windows so work roots stay uncluttered.
    if os.name == "nt":
        subprocess.run(["attrib", "+h", str(ms_root)], capture_output=True, check=False)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(10):
        run_id = f"{stamp}-{secrets.token_hex(3)}"
        run_root = ms_root / run_id
        try:
            run_root.mkdir()
            break
        except FileExistsError:
            continue
        except OSError as exc:
            return error(f"cannot create run_root: {exc}")
    else:
        return error("could not allocate a unique run_id")

    project_value = str(project_root) if project_root is not None else "NOT_SELECTED"
    try:
        (run_root / "record").mkdir()
        log_path = run_root / "log.md"
        with log_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(build_log(run_id, source, work_root, run_root, project_value, args.mode, args.review_policy))
    except OSError as exc:
        return error(f"cannot initialize run files: {exc}")

    print(json.dumps({
        "status": "RUNNING",
        "run_id": run_id,
        "work_root": str(work_root),
        "v1_source": str(source),
        "run_root": str(run_root),
        "log_path": str(log_path),
        "record_root": str(run_root / "record"),
        "project_root": str(project_root) if project_root is not None else None,
        "mode": args.mode,
        "review_policy": args.review_policy,
        "install_attempt": 0,
        "build_attempt": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

