#!/usr/bin/env python3
"""Read official catalogs and Gitee repository candidates; never infer equivalence or fork."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://resource.mindplus.top/mindplus/"
MODES = {"rt": "realtime", "ul": "upload", "py": "python-block", "mpy": "micropython-block"}
MAX_BYTES = 8 * 1024 * 1024
PUBLICATION_TOPIC = "MindPlus-Ext2"


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url):
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in {"resource.mindplus.top", "gitee.com"} or p.username or p.password or p.port not in (None, 443):
        raise ValueError("unsupported catalog URL")


def fetch(url):
    check_url(url)
    with urllib.request.build_opener(SafeRedirect()).open(url, timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("catalog exceeds download limit")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) != len(raw):
            raise ValueError("truncated catalog response")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise ValueError("catalog must be an array of objects")
    return value, hashlib.sha256(raw).hexdigest()


def terms(value):
    if isinstance(value, list):
        return set().union(*(terms(x) for x in value))
    if isinstance(value, dict):
        return {str(x).strip().casefold() for x in value.values() if isinstance(x, str) and x.strip()}
    return {x.strip().casefold() for x in re.split(r"[|,;]", str(value or "")) if x.strip()}


def match_entries(entries, query):
    needles = set().union(*(terms(query.get(key)) for key in ("id", "compatibilityId", "sku", "name", "keywords")))
    matches = []
    for entry in entries:
        reasons = [key for key in ("id", "compatibilityId", "sku", "name") if terms(entry.get(key)) & needles]
        text = json.dumps({k: entry.get(k) for k in ("name", "description", "path")}, ensure_ascii=False).casefold()
        if not reasons and any(len(n) >= 3 and n in text for n in needles):
            reasons = ["text_candidate"]
        if reasons:
            same_id = bool(query.get("id")) and entry.get("id") == query.get("id")
            same_author = bool(query.get("author")) and entry.get("author") == query.get("author")
            identity = "SAME_LIBRARY" if same_id and same_author else "ID_COLLISION" if same_id else "RELATED_CANDIDATE"
            # Gitee's repository id is numeric and owner is not config.author.
            if "full_name" in entry or "html_url" in entry:
                identity = "REPOSITORY_CONFIG_UNVERIFIED"
            matches.append({"matched_fields": reasons, "entry": entry, "identity": identity})
    return matches


def collision_folder(folder, author, author_slug=None):
    if not re.fullmatch(r"ext2-(rt|ul|py|mpy)-[A-Za-z0-9][A-Za-z0-9_-]*", folder):
        raise ValueError("folder must retain the standard mode prefix")
    slug = author if re.fullmatch(r"[A-Za-z0-9]+", author or "") else author_slug
    if not slug or not re.fullmatch(r"[A-Za-z0-9]+", slug):
        raise ValueError("provide the author's verified pinyin/ASCII slug; do not guess a Chinese pronunciation")
    suffix = "-" + slug
    return folder if folder.casefold().endswith(suffix.casefold()) else folder + suffix


def verify_selection(project, data):
    if not isinstance(data, dict) or data.get("schema_version") != "mindplus.review-lite-selection/v1":
        raise ValueError("invalid Lite selection schema")
    if data.get("status") != "PASS" or not data.get("comparison") or not data.get("source_decision"):
        raise ValueError("Lite requires completed comparison and source decision")
    if Path(data.get("project_root", "")).resolve() != project.resolve():
        raise ValueError("Lite selection belongs to another project")
    if data.get("decision") not in {"NO_DUPLICATE", "ID_COLLISION_RENAMED", "FORK_EXISTING", "ALREADY_BASE", "EXPLICIT_SOURCE_UNVERIFIED"}:
        raise ValueError("Lite source selection is unresolved")
    if data["decision"] == "ID_COLLISION_RENAMED":
        expected = collision_folder(data.get("original_folder", ""), data.get("author", ""), data.get("author_slug"))
        if project.name != expected:
            raise ValueError("id-only collision requires the author suffix in the project folder")
    if data["decision"] == "FORK_EXISTING" and (data.get("fork_verified") is not True or not data.get("repository") or not data.get("original_repository")):
        raise ValueError("Lite fork must be verified before source edits")
    if data["decision"] == "EXPLICIT_SOURCE_UNVERIFIED":
        if not data.get("limitation"):
            raise ValueError("Unverified Lite needs an explicit source decision and limitation")
        return
    path = Path(data.get("candidate_report", ""))
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Lite candidate report is missing")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != data.get("candidate_sha256"):
        raise ValueError("Lite candidate report changed")
    report = json.loads(raw)
    if report.get("status") != "CANDIDATES_READY":
        raise ValueError("Incomplete catalog search cannot establish absence or complete Lite")
    query = report.get("query", {})
    if not query.get("author") or not query.get("id"):
        raise ValueError("Complete Lite needs the intended config.author and config.id")
    if data["decision"] == "ID_COLLISION_RENAMED" and data.get("author") != query["author"]:
        raise ValueError("Folder suffix must use the queried author identity")
    for candidate in (project / "extension/public/config.json", project / "config.json"):
        if candidate.is_file():
            config = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if any(key in config and config[key] != query[key] for key in ("author", "id")):
                raise ValueError("Lite query does not match the produced config identity")
            break
    identities = {c.get("identity") for src in report.get("sources", []) for c in src.get("candidates", [])}
    for item in data.get("repository_configs", []):
        config_path = Path(item["path"])
        content = config_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != item.get("sha256"):
            raise ValueError("Gitee config evidence changed")
        config = json.loads(content)
        identities.update(c["identity"] for c in match_entries([config], query))
    if "SAME_LIBRARY" in identities and data["decision"] not in {"FORK_EXISTING", "ALREADY_BASE"}:
        raise ValueError("Same author and id requires existing-base/fork development")
    if "SAME_LIBRARY" in identities and not data.get("repository"):
        raise ValueError("Same-library selection requires the verified development repository")
    if "SAME_LIBRARY" not in identities and "ID_COLLISION" in identities and data["decision"] != "ID_COLLISION_RENAMED":
        raise ValueError("Different author with same extension id requires the author suffix")


def inspect(mode, kind, query, reader=fetch):
    if kind == "device" and mode == "py":
        raise ValueError("no official Python device catalog was supplied; do not invent one")
    suffix = "devices/dev.json" if kind == "device" else "extensions/ext.json"
    url = BASE + MODES[mode] + "/" + suffix
    report = {"schema_version": "mindplus.review-lite/v1", "mode": mode, "kind": kind,
              "query": query, "checked_at": datetime.now(timezone.utc).isoformat(), "sources": []}
    try:
        entries, digest = reader(url)
        report["sources"].append({"url": url, "sha256": digest, "complete": True,
                                  "candidates": match_entries(entries, query)})
    except (OSError, ValueError) as exc:
        report["sources"].append({"url": url, "complete": False, "error": str(exc)})
    complete = False
    try:
        for page in range(1, 11):
            repo_url = f"https://gitee.com/api/v5/search/repositories?q={PUBLICATION_TOPIC}&page={page}&per_page=100"
            batch, digest = reader(repo_url)
            report["sources"].append({"url": repo_url, "sha256": digest, "scope": {"type": "topic", "name": PUBLICATION_TOPIC},
                                      "complete": len(batch) < 100,
                                      "candidates": match_entries(batch, query)})
            if len(batch) < 100:
                complete = True
                break
    except (OSError, ValueError) as exc:
        report["sources"].append({"url": repo_url, "complete": False, "error": str(exc)})
    report["status"] = "CANDIDATES_READY" if report["sources"][0]["complete"] and complete else "UNVERIFIED"
    report["decision"] = "PENDING_SEMANTIC_COMPARISON"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--kind", choices=["extension", "device"], default="extension")
    parser.add_argument("--query", type=Path, required=True, help="JSON with id, compatibilityId, sku, name or keywords")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folder", help="proposed standard project folder name")
    parser.add_argument("--author-slug", help="verified pinyin for a non-ASCII author")
    args = parser.parse_args()
    query = json.loads(args.query.read_text(encoding="utf-8-sig"))
    if not isinstance(query, dict) or not any(terms(query.get(k)) for k in ("id", "compatibilityId", "sku", "name", "keywords")):
        parser.error("provide at least one concrete identity or search keyword")
    report = inspect(args.mode, args.kind, query)
    identities = {c["identity"] for src in report["sources"] for c in src.get("candidates", [])}
    if args.folder and "ID_COLLISION" in identities and "SAME_LIBRARY" not in identities:
        report["suggested_folder"] = collision_folder(args.folder, query.get("author", ""), args.author_slug)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "CANDIDATES_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
