#!/usr/bin/env python3
"""Read-only search and fetch from the official Mind+ Gitee organization (corpus fallback).

Public GET endpoints only: no token, no login, no mutation. Downloaded files are data
evidence with a provenance record; never execute fetched content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ORG = "mind-plus"
API_BASE = "https://gitee.com/api/v5"
RAW_BASE = "https://gitee.com"
USER_AGENT = "mindplus-extension-skills/official-corpus-fallback"
REQUEST_TIMEOUT = 20


class FetchError(RuntimeError):
    pass


def emit(value: dict[str, Any], code: int) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return code


def http_get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"GET failed: {url}: {exc}") from exc


def http_get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"GET failed: {url}: {exc}") from exc


def default_branch(repo: str) -> str:
    detail = http_get_json(f"{API_BASE}/repos/{ORG}/{repo}")
    branch = detail.get("default_branch") if isinstance(detail, dict) else None
    return str(branch) if branch else "master"


def cmd_list(args: argparse.Namespace) -> int:
    repositories: list[dict[str, Any]] = []
    page = args.page or 1
    if page < 1:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.INVALID_PAGE", "error": "page must be positive"}, 2)
    first_page = page
    reached_end = False
    try:
        while True:
            batch = http_get_json(f"{API_BASE}/orgs/{ORG}/repos?page={page}&per_page=100")
            if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
                raise FetchError("Repository listing returned an invalid response; absence cannot be determined")
            repositories.extend(batch)
            reached_end = len(batch) < 100
            if reached_end or args.page or page >= 10:
                break
            page += 1
    except FetchError as exc:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.NETWORK", "error": str(exc)}, 2)

    entries = [
        {
            "name": item.get("path") or item.get("name"),
            "description": item.get("description"),
            "url": item.get("html_url"),
            "updated_at": item.get("updated_at"),
        }
        for item in repositories
    ]
    if args.search:
        needle = args.search.casefold()
        entries = [entry for entry in entries if needle in (str(entry["name"]) + " " + str(entry.get("description") or "")).casefold()]
    return emit(
        {
            "status": "PASS",
            "org": ORG,
            "count": len(entries),
            "first_page": first_page,
            "last_page": page,
            "reached_end": reached_end,
            "complete": first_page == 1 and reached_end,
            "next_page": None if reached_end else page + 1,
            "repositories": entries,
            "next_command": "python scripts/switch/fetch_official_reference.py tree --repo <name>  to locate config.json, then fetch",
        },
        0,
    )


def cmd_tree(args: argparse.Namespace) -> int:
    ref = args.ref or default_branch(args.repo)
    try:
        listing = http_get_json(f"{API_BASE}/repos/{ORG}/{args.repo}/contents/{args.path}?ref={ref}")
    except FetchError as exc:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.NETWORK", "error": str(exc)}, 2)
    if not isinstance(listing, list):
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.NOT_A_DIRECTORY", "repo": args.repo, "path": args.path}, 2)
    entries = [
        {"name": item.get("name"), "type": item.get("type"), "path": item.get("path")}
        for item in listing
        if isinstance(item, dict)
    ]
    return emit(
        {
            "status": "PASS",
            "repo": args.repo,
            "ref": ref,
            "path": args.path,
            "entries": entries,
            "next_command": "python scripts/switch/fetch_official_reference.py fetch --repo <repo> --path <file> --evidence-dir <run_root>/record/official-corpus",
        },
        0,
    )


def safe_evidence_name(repo: str, path: str) -> str:
    merged = f"{repo}--{path}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", merged)


def cmd_fetch(args: argparse.Namespace) -> int:
    ref = args.ref or default_branch(args.repo)
    raw_url = f"{RAW_BASE}/{ORG}/{args.repo}/raw/{ref}/{args.path}"
    try:
        content = http_get_bytes(raw_url)
    except FetchError as exc:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.NETWORK", "error": str(exc)}, 2)

    evidence_dir = args.evidence_dir.expanduser().resolve(strict=False)
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        target = evidence_dir / safe_evidence_name(args.repo, args.path)
        target.write_bytes(content)
    except OSError as exc:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.WRITE", "error": str(exc)}, 2)

    sha256 = hashlib.sha256(content).hexdigest()
    provenance = {
        "schema_version": 1,
        "source": "official-gitee-org",
        "org": ORG,
        "repo": args.repo,
        "path": args.path,
        "ref": ref,
        "url": raw_url,
        "sha256": sha256,
        "size": len(content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "C2-official",
        "note": "Data evidence only; never execute fetched content.",
    }
    provenance_path = evidence_dir / f"{safe_evidence_name(args.repo, args.path)}.provenance.json"
    try:
        with provenance_path.open("w", encoding="utf-8", newline="\n") as output_handle:
            output_handle.write(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        return emit({"status": "BLOCKED", "reason_code": "OFFICIAL_CORPUS.WRITE", "error": str(exc)}, 2)

    return emit(
        {
            "status": "PASS",
            "repo": args.repo,
            "path": args.path,
            "ref": ref,
            "url": raw_url,
            "sha256": sha256,
            "evidence_file": str(target),
            "provenance_file": str(provenance_path),
            "next_command": "Read the evidence file for the convention you needed; record evidence_file in the run log or spec with what was adopted from it.",
        },
        0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List official organization repositories")
    list_parser.add_argument("--search", help="Client-side filter by name/description substring")
    list_parser.add_argument("--page", type=int, help="Single page to fetch (default: paginate up to 10 pages)")
    list_parser.set_defaults(handler=cmd_list)

    tree_parser = subparsers.add_parser("tree", help="List one repository directory")
    tree_parser.add_argument("--repo", required=True)
    tree_parser.add_argument("--path", default="")
    tree_parser.add_argument("--ref")
    tree_parser.set_defaults(handler=cmd_tree)

    fetch_parser = subparsers.add_parser("fetch", help="Download one file with a provenance record")
    fetch_parser.add_argument("--repo", required=True)
    fetch_parser.add_argument("--path", required=True)
    fetch_parser.add_argument("--ref")
    fetch_parser.add_argument("--evidence-dir", required=True, type=Path)
    fetch_parser.set_defaults(handler=cmd_fetch)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
