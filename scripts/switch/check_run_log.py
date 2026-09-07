#!/usr/bin/env python3
"""Validate the structured terminal state of a MindPlus-Switch run log."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FIELD_RE = re.compile(r"^- ([A-Za-z0-9_-]+): (.*)$")
CHECKPOINT_RE = re.compile(r"^- \[([ xX])\] (S-1|S\d+)\s+.*$")
EVENT_RE = re.compile(r"^- \[[^]]+\] \[(S-1|S\d+)\] \[([A-Z]+)\]")
STEP_ORDER = {"S-1": -1, **{f"S{i}": i for i in range(12)}}


def parse_log(path: Path) -> tuple[dict[str, str], dict[str, bool], list[tuple[str, str]], list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    fields: dict[str, str] = {}
    steps: dict[str, bool] = {}
    events: list[tuple[str, str]] = []
    errors: list[str] = []
    for line in text.splitlines():
        field = FIELD_RE.match(line)
        if field:
            key, value = field.groups()
            if key in fields:
                # The template has a nested Reference Evidence `status`, while
                # the first `status` is the terminal run status. Keep the first
                # occurrence for this known legacy shape.
                if key != "status":
                    errors.append(f"duplicate structured field: {key}")
            else:
                fields[key] = value.strip()
        checkpoint = CHECKPOINT_RE.match(line)
        if checkpoint:
            marker, step = checkpoint.groups()
            if step in steps:
                errors.append(f"duplicate checkpoint: {step}")
            steps[step] = marker.lower() == "x"
        event = EVENT_RE.match(line)
        if event:
            events.append(event.groups())
    return fields, steps, events, errors


def integer(fields: dict[str, str], key: str, errors: list[str]) -> int | None:
    value = fields.get(key, "")
    try:
        return int(value)
    except ValueError:
        errors.append(f"{key} must be an integer, got {value!r}")
        return None


def unset(value: str | None) -> bool:
    return value is None or value in {"", "NONE", "NOT_RUN"}


def validate(
    fields: dict[str, str],
    steps: dict[str, bool],
    events: list[tuple[str, str]],
    errors: list[str],
) -> None:
    status = fields.get("status", "")
    base_status = status.split(" ", 1)[0]
    current_step = fields.get("current_step", "")
    if not status:
        errors.append("missing status")
    elif base_status == "RUNNING":
        errors.append("terminal log still has status RUNNING")
    if current_step in {"", "S-1"}:
        errors.append("terminal log has no completed current_step")
    if not steps.get("S11", False):
        errors.append("S11 HANDOFF is not marked as processed")

    previous_order = -1
    for step, _result in events:
        current_order = STEP_ORDER.get(step)
        if current_order is None:
            errors.append(f"event contains unknown step: {step}")
            continue
        if current_order < previous_order:
            errors.append(f"event order regressed: {step} appears after a later step")
        previous_order = max(previous_order, current_order)

    install_attempt = integer(fields, "install_attempt", errors)
    build_attempt = integer(fields, "build_attempt", errors)
    install_status = fields.get("install_status", "NOT_RUN")
    build_status = fields.get("build_status", "NOT_RUN")
    install_exit = fields.get("install_exit", "NOT_RUN")
    build_exit = fields.get("build_exit", "NOT_RUN")

    if install_attempt is not None:
        if install_attempt not in {0, 1}:
            errors.append("install_attempt must be 0 or 1")
        if install_attempt == 1 and install_status == "NOT_RUN":
            errors.append("install_attempt=1 but install_status is NOT_RUN")
        if install_status == "PASS" and install_attempt != 1:
            errors.append("install_status=PASS requires install_attempt=1")
    if build_attempt is not None:
        if build_attempt not in {0, 1}:
            errors.append("build_attempt must be 0 or 1")
        if build_attempt == 1 and build_status == "NOT_RUN":
            errors.append("build_attempt=1 but build_status is NOT_RUN")
        if build_status == "PASS" and build_attempt != 1:
            errors.append("build_status=PASS requires build_attempt=1")

    if install_status == "PASS" and install_exit != "0":
        errors.append("install_status=PASS requires install_exit=0")
    if build_status == "PASS" and build_exit != "0":
        errors.append("build_status=PASS requires build_exit=0")
    if install_status == "USER_ACTION_REQUIRED":
        if build_status != "SKIPPED_DEPENDENCY":
            errors.append("stalled install requires build_status=SKIPPED_DEPENDENCY")
        if build_attempt not in {None, 0}:
            errors.append("stalled install must not start a build attempt")
    if build_status == "SKIPPED_DEPENDENCY" and install_status == "PASS":
        errors.append("build cannot be skipped as a dependency after a passing install")
    if build_status == "USER_ACTION_REQUIRED" and install_status != "PASS":
        errors.append("stalled build requires install_status=PASS")
    if install_status == "FAIL" and any(step in {f"S{i}" for i in range(5, 11)} for step, _ in events):
        errors.append("non-zero install failure cannot be followed by conversion/build steps")

    # A checkpoint marked as processed must have a corresponding structured fact.
    if steps.get("S1", False):
        if unset(fields.get("candidates")):
            errors.append("S1 is processed but route candidates are not recorded")
        if unset(fields.get("selected")):
            errors.append("S1 is processed but selected mode is not recorded")
    if steps.get("S2", False) and unset(fields.get("reference_selection")):
        errors.append("S2 is processed but reference_selection is not recorded")
    if steps.get("S7", False) and unset(fields.get("copy_check")):
        errors.append("S7 is processed but copy_check is not recorded")
    if steps.get("S8", False) and unset(fields.get("readme_check")):
        errors.append("S8 is processed but readme_check is not recorded")
    if steps.get("S9", False) and unset(fields.get("conversion_check")):
        errors.append("S9 is processed but conversion_check is not recorded")

    user_action = fields.get("user_action_required", "NONE")
    next_workflow = fields.get("next_workflow", "NOT_RUN")
    if base_status == "HANDED_OFF":
        if user_action == "NONE":
            errors.append("HANDED_OFF requires user_action_required")
        if unset(next_workflow):
            errors.append("HANDED_OFF requires next_workflow")
        if install_status != "USER_ACTION_REQUIRED" and build_status != "USER_ACTION_REQUIRED":
            errors.append("HANDED_OFF requires an install or build user-action status")
    if base_status == "CONVERTED_BUILD_PASS":
        if install_status != "PASS" or build_status != "PASS":
            errors.append("CONVERTED_BUILD_PASS requires PASS install and build statuses")
        if not steps.get("S10", False):
            errors.append("CONVERTED_BUILD_PASS requires processed S10")
    if steps.get("S10", False) and build_status == "NOT_RUN":
        errors.append("S10 is processed but build_status is NOT_RUN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    args = parser.parse_args()
    path = args.log.expanduser().resolve()
    try:
        fields, steps, events, errors = parse_log(path)
        validate(fields, steps, events, errors)
    except OSError as exc:
        result = {"status": "BLOCKED", "reason_code": "WORKSPACE", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    result = {
        "status": "PASS" if not errors else "FAIL",
        "log": str(path),
        "terminal_status": fields.get("status", "NOT_RUN"),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

