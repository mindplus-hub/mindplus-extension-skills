#!/usr/bin/env python3
"""Create one MindPlus-Switch record directory and its checkpoint log."""

from __future__ import annotations

import argparse
import re
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

- S-1: run records created under .mindplus-agent; the final project remains outside the records tree.

## Event Log

- [{datetime.now(timezone.utc).isoformat()}] [S-1] created run log
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--v1-source", required=True, type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--parent-run-id", help="Bind conversion records to an existing parent task")
    parser.add_argument("--mode", default="UNKNOWN", choices=["UNKNOWN", "UPLOAD", "PYTHON_BLOCK", "MICROPYTHON", "REALTIME"])
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

    ms_root = work_root / ".mindplus-agent"
    if inside(ms_root, source):
        return error(".mindplus-agent would be created inside v1_source; choose a separate work_root")
    if project_root is not None:
        if not re.fullmatch(r"ext2-(?:rt|ul|py|mpy)-[A-Za-z0-9][A-Za-z0-9_-]*", project_root.name):
            return error("fresh project_root must be named ext2-<rt|ul|py|mpy>-<name>")
        if inside(project_root, source) or inside(source, project_root):
            return error("project_root and v1_source must be separate directory trees")
        if inside(project_root, ms_root) or inside(ms_root, project_root):
            return error("project_root and .mindplus-agent must be separate directory trees")

    try:
        ms_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return error(f"cannot create .mindplus-agent directory: {exc}")

    # .mindplus-agent stores conversion records only; hide it on Windows so work roots stay uncluttered.
    if os.name == "nt":
        subprocess.run(["attrib", "+h", str(ms_root)], capture_output=True, check=False)

    parent_root = None
    binding = {"schema_version": "mindplus-agent.conversion-record/v1", "parent_run_id": args.parent_run_id,
               "v1_source": str(source), "project_root": str(project_root) if project_root else None,
               "mode": args.mode, "review_policy": args.review_policy}
    if args.parent_run_id:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.parent_run_id):
            return error("invalid parent run id")
        parent_root = ms_root / "runs" / args.parent_run_id
        try:
            parent = json.loads((parent_root / "run.json").read_text(encoding="utf-8"))
            request = json.loads((parent_root / "request.json").read_text(encoding="utf-8"))
            paths = request["paths"]
            if parent.get("state") == "TERMINAL" or parent.get("current_workflow") != "CONVERT_FRESH":
                return error("parent must be an active CONVERT_FRESH run")
            if Path(paths["v1_source"]).resolve() != source or project_root != Path(paths["project_root"]).resolve():
                return error("conversion paths do not match the immutable parent request")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return error(f"cannot validate parent run: {exc}")
        run_id = args.parent_run_id
        run_root = parent_root / "children" / "CONVERT_FRESH"
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}-{secrets.token_hex(6)}"
        run_root = ms_root / "conversions" / run_id
    if run_root.exists():
        try:
            saved = json.loads((run_root / "record.json").read_text(encoding="utf-8"))
            if saved != binding or not (run_root / "log.md").is_file() or not (run_root / "record").is_dir():
                return error("existing conversion record conflicts or is incomplete; do not overwrite")
        except (OSError, ValueError) as exc:
            return error(f"cannot resume conversion record: {exc}")
        print(json.dumps({"status": "PASS_IDEMPOTENT", "run_id": run_id, "parent_run_id": args.parent_run_id,
                          "run_root": str(run_root), "log_path": str(run_root / "log.md"),
                          "record_root": str(run_root / "record")}, ensure_ascii=False))
        return 0
    try:
        run_root.mkdir(parents=True)
    except OSError as exc:
        return error(f"cannot create conversion run: {exc}")

    project_value = str(project_root) if project_root is not None else "NOT_SELECTED"
    try:
        (run_root / "record.json").write_text(json.dumps(binding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (run_root / "record").mkdir()
        log_path = run_root / "log.md"
        with log_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(build_log(run_id, source, work_root, run_root, project_value, args.mode, args.review_policy))
    except OSError as exc:
        return error(f"cannot initialize run files: {exc}")

    print(json.dumps({
        "status": "RUNNING",
        "parent_run_id": args.parent_run_id,
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

