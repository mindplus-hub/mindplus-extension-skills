#!/usr/bin/env python3
"""Update one checkpoint and top-level state in a MindPlus-Switch run log."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_STEPS = {f"S{i}" for i in range(13)} | {"S-1"}
ALLOWED_RESULTS = {"PASS", "FAIL", "BLOCKED", "RUNNING"}
ALLOWED_FIELDS = {
    "project_root", "extension_root", "status", "mode", "reference_status",
    "reference_release", "reference_root", "reference_selection", "install_attempt",
    "build_attempt", "install_status", "install_exit", "install_stall", "build_status",
    "build_exit", "build_stall", "user_action_required", "next_workflow", "review_status",
    "identity_mapping", "compatibility_id", "conversion_check", "copy_check", "readme_check",
    "candidates", "selected", "source_anomalies", "intervention", "initial_inventory",
    "pre_conversion_inventory", "snapshot_compare", "snapshot_match", "release_id",
    "content_sha256", "supported_modes", "active_root", "selection_file", "topics_loaded",
    "scaffold_release", "scaffold_url", "scaffold_sha256", "inherited_git",
    "examples_present", "node_version", "npm_version", "npm_install_exit",
    "package_lock_change",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--step", required=True)
    parser.add_argument("--result", required=True, choices=sorted(ALLOWED_RESULTS))
    parser.add_argument("--status")
    parser.add_argument("--field", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--event", required=True)
    args = parser.parse_args()

    if args.step not in ALLOWED_STEPS:
        print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": "unknown step"}))
        return 2
    # --event is appended as a whole log line, so an embedded newline would forge
    # additional entries in the record this pipeline later reviews as evidence.
    if "\n" in args.event or "\r" in args.event:
        print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": "event must not contain newlines"}))
        return 2
    path = args.log.expanduser().resolve()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "WORKSPACE", "error": str(exc)}))
        return 2

    # A checkpoint records that the step reached a terminal result. BLOCKED and
    # FAIL are intentionally checked so a handoff cannot look unfinished merely
    # because the step did not succeed.
    checked = " " if args.result == "RUNNING" else "x"
    text, count = re.subn(
        rf"(?m)^- \[[ x]\] ({re.escape(args.step)}\s+[^\r\n]+)$",
        rf"- [{checked}] \1",
        text,
        count=1,
    )
    if count != 1:
        print(json.dumps({"status": "BLOCKED", "reason_code": "LOG_FORMAT", "error": "checkpoint not found"}))
        return 2
    text = re.sub(r"(?m)^- current_step: .+$", f"- current_step: {args.step}", text, count=1)
    if args.status:
        text = re.sub(r"(?m)^- status: .+$", f"- status: {args.status}", text, count=1)
    for assignment in args.field:
        if "=" not in assignment:
            print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": "field must be KEY=VALUE"}))
            return 2
        key, value = assignment.split("=", 1)
        if key not in ALLOWED_FIELDS or "\n" in value or "\r" in value:
            print(json.dumps({"status": "BLOCKED", "reason_code": "INPUT", "error": f"invalid field: {key}"}))
            return 2
        # Use a callable replacement so Windows paths such as C:\\work\\ext
        # are inserted literally instead of being parsed as replacement escapes.
        text, field_count = re.subn(
            rf"(?m)^- {re.escape(key)}: .+$",
            lambda _match, key=key, value=value: f"- {key}: {value}",
            text,
            count=1,
        )
        if field_count != 1:
            print(json.dumps({"status": "BLOCKED", "reason_code": "LOG_FORMAT", "error": f"field not found: {key}"}))
            return 2
    stamp = datetime.now(timezone.utc).isoformat()
    text = text.rstrip() + f"\n- [{stamp}] [{args.step}] [{args.result}] {args.event}\n"
    try:
        with path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(text)
    except OSError as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "WORKSPACE", "error": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "log": str(path), "step": args.step, "result": args.result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

