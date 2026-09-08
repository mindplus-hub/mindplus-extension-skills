#!/usr/bin/env python3
"""Build and check a shallow WorkBuddy package without modifying the source skill.

Standard library only. Local builds are offline; --publish explicitly uploads to Gitee Releases.
Every build gets a new output directory; existing builds are never overwritten.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
GENERATED = "references/switch/generated/"
IGNORED = {".git", "__pycache__", ".ms", ".mindplus-agent", "node_modules", "dist"}

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from check_gitee_token import resolve_windows_credential


class PackageError(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PackageError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mapped_path(relative: str) -> str:
    p = PurePosixPath(relative)
    if relative.startswith(GENERATED):
        return "assets/" + "__".join(p.parts[3:])
    if p.parts[0] in {"scripts", "references", "agents"}:
        return p.parts[0] + "/" + "__".join(p.parts[1:])
    return relative


def collect(source: Path) -> dict[str, bytes]:
    files = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink() or (getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise PackageError(f"Source contains a link/reparse point: {relative}")
        if not path.is_file():
            continue
        if relative.parts[0] in {"scripts", "references", "agents"} or relative.name in {"SKILL.md", "VERSION", "LICENSE", "LICENSE.md", "LICENSE.txt", "NOTICE", "THIRD_PARTY_NOTICES.md"}:
            if path.suffix in {".pyc", ".pyo"}:
                continue
            files[relative.as_posix()] = path.read_bytes()
    if "SKILL.md" not in files or "scripts/mpa.py" not in files:
        raise PackageError("Source is not the expected mindplus-agent-skill package")
    mapping = {old: mapped_path(old) for old in files}
    names = [name.casefold() for name in mapping.values()]
    if len(names) != len(set(names)):
        raise PackageError("Flattening produces a duplicate/case-colliding filename")
    if any(len(PurePosixPath(name).parts) > 2 for name in mapping.values()):
        raise PackageError("An unsupported source path cannot be flattened safely")
    return files


def verify_source_corpus(files: dict[str, bytes]) -> None:
    manifest = json.loads(files[GENERATED + "manifest.json"])
    entries = manifest["files"]
    declared = {item["path"] for item in entries}
    actual = {name[len(GENERATED):] for name in files if name.startswith(GENERATED)} - {"manifest.json"}
    if declared != actual or len(declared) != len(entries):
        raise PackageError("Source corpus file set does not match its manifest")
    for item in entries:
        data = files[GENERATED + item["path"]]
        if len(data) != item["size"] or sha(data) != item["sha256"]:
            raise PackageError(f"Source corpus integrity failed: {item['path']}")
    if corpus_hash(entries) != manifest["content_sha256"]:
        raise PackageError("Source corpus aggregate hash is invalid")


def corpus_hash(entries: list[dict]) -> str:
    return sha("".join(f"{x['path']}\0{x['sha256']}\0{x['size']}\n" for x in sorted(entries, key=lambda x: x["path"])).encode())


def load_metadata(path: Path, preview: bool) -> dict:
    info = read_json(path)
    for key, value in info.items():
        if not isinstance(value, str):
            raise PackageError(f"Metadata {key} must be a string")
    for key in ("name", "description", "description_zh", "version", "repository"):
        if not isinstance(info.get(key), str) or not info[key].strip():
            raise PackageError(f"release-info.json needs a non-empty {key}")
    if info["name"] != "mindplus-agent-skill":
        raise PackageError("Keep name=mindplus-agent-skill; this adapter targets that skill")
    if not re.fullmatch(r"\d+\.\d+\.\d+", info["version"]):
        raise PackageError("version must be a stable release version such as 0.1.1")
    for field in ("description", "description_zh", "description_en"):
        if len(info.get(field, "")) > 1024:
            raise PackageError(f"{field} exceeds 1024 characters")
    if len(info.get("compatibility", "")) > 500:
        raise PackageError("compatibility exceeds 500 characters")
    author = info.get("author", "")
    if not isinstance(author, str):
        raise PackageError("author must be a string")
    if not author.strip() or re.search(r"待填|待确认|TODO|REPLACE", author, re.I):
        if not preview:
            raise PackageError("Fill in the real team author first; --preview permits draft metadata")
        info["author"] = "PREVIEW-TEAM-NOT-SET"
    return info


class Adapter:
    def __init__(self, files: dict[str, bytes]):
        self.mapping = {name: mapped_path(name) for name in files}
        self.directories = {
            "scripts/switch": "scripts", "references/workflows": "references",
            "references/contracts": "references", "references/switch/generated": "assets",
            "references/switch": "references",
        }
        for name in files:
            if name.startswith(GENERATED):
                parent = PurePosixPath(name).parent
                while len(parent.parts) >= 3:
                    self.directories[str(parent)] = "assets"
                    parent = parent.parent
        self.targets = {**self.directories, **self.mapping}
        # Longest first, one pass: generated output is never rewritten a second time.
        self.pattern = re.compile(r"(?<![A-Za-z0-9_:/.-])/?(?:" + "|".join(re.escape(x) for x in sorted(self.targets, key=len, reverse=True)) + r")(?=$|[^A-Za-z0-9_.-])")

    def root_paths(self, text: str) -> str:
        return self.pattern.sub(lambda m: ("/" if m.group(0).startswith("/") else "") + self.targets[m.group(0).lstrip("/")], text)

    def markdown(self, text: str, old: str) -> str:
        new = self.mapping[old]

        def link(match):
            target = match.group(1)
            if "://" in target or target.startswith(("#", "mailto:")):
                return match.group(0)
            raw, marker, anchor = target.partition("#")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(old), raw))
            dest = self.targets.get(resolved)
            if dest is None:
                return match.group(0)
            relative = posixpath.relpath(dest, posixpath.dirname(new) or ".")
            return "](" + relative + (marker + anchor if marker else "") + ")"

        # Root paths outside Markdown links are also used as copyable commands.
        pieces = re.split(r"(\]\([^)]*\))", text)
        return "".join(re.sub(r"\]\(([^)]+)\)", link, part) if part.startswith("](") else self.root_paths(part) for part in pieces)

    def python(self, text: str, old: str) -> str:
        # Deliberate, fail-closed adapters for dynamic paths that are not literals.
        if old.startswith("scripts/switch/"):
            text = text.replace("Path(__file__).resolve().parents[2]", "Path(__file__).resolve().parents[1]")
        if old == "scripts/mpa.py":
            for leaf in ("switch.md", "create.md", "review.md", "gitee-publish.md"):
                text = text.replace('"' + leaf + '"', '"workflows__' + leaf + '"')
        if old == "scripts/switch/check_reference_release.py":
            replacements = {
                'bundled_root = switch_reference_root / "generated"': 'bundled_root = skill_root / "assets"',
                'switch_reference_root / "release-channel.json"': 'switch_reference_root / "switch__release-channel.json"',
                '"MINDPLUS_AGENT_SWITCH_CACHE"': '"MINDPLUS_AGENT_WORKBUDDY_CACHE"',
                '"MindPlus-Agent-Skill"': '"MindPlus-Agent-Skill-WorkBuddy"',
                '"mindplus-agent-skill"': '"mindplus-agent-skill-workbuddy"',
            }
            for before, after in replacements.items():
                if before not in text:
                    raise PackageError(f"Source adapter needs updating: {old}: {before}")
                text = text.replace(before, after)
        adapter = self

        # AST offsets are UTF-8 byte offsets, including on Python 3.9.0.
        encoded = text.encode("utf-8")
        lines = encoded.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        edits = []

        def replace(node, replacement):
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            edits.append((start, end, replacement.encode("utf-8")))

        class Paths(ast.NodeVisitor):
            def visit_BinOp(self, node):
                parts = []
                base = node
                while isinstance(base, ast.BinOp) and isinstance(base.op, ast.Div) and isinstance(base.right, ast.Constant) and isinstance(base.right.value, str):
                    parts.insert(0, base.right.value)
                    base = base.left
                dest = adapter.targets.get("/".join(parts))
                if dest is not None:
                    original_base = ast.get_source_segment(text, base)
                    replace(node, "(" + original_base + ")" + "".join(" / " + repr(part) for part in PurePosixPath(dest).parts))
                    return
                self.generic_visit(node)

            def visit_JoinedStr(self, node):
                # Never unparse f-strings: 3.9.0 can insert illegal backslashes.
                original = ast.get_source_segment(text, node)
                changed = adapter.root_paths(original)
                if changed != original:
                    replace(node, changed)

            def visit_Constant(self, node):
                if isinstance(node.value, str):
                    changed = adapter.root_paths(node.value)
                    if changed != node.value:
                        replace(node, repr(changed))

        Paths().visit(ast.parse(text, filename=old))
        for start, end, replacement in sorted(edits, reverse=True):
            encoded = encoded[:start] + replacement + encoded[end:]
        result = encoded.decode("utf-8")
        ast.parse(result, filename=old)
        return result



def build_files(source_files: dict[str, bytes], info: dict, preview: bool) -> tuple[dict[str, bytes], dict]:
    adapter = Adapter(source_files)
    result = {}
    for old, data in source_files.items():
        name = adapter.mapping[old]
        if old.endswith(".py"):
            data = adapter.python(data.decode("utf-8-sig"), old).encode("utf-8")
        elif old.endswith(".md"):
            data = adapter.markdown(data.decode("utf-8-sig"), old).encode("utf-8")
        elif old.endswith(".json"):
            data = adapter.root_paths(data.decode("utf-8-sig")).encode("utf-8")
            json.loads(data)
        result[name] = data
    # Generated reference topics retain their identities and provenance, but get new paths.
    index = json.loads(result["assets/index.json"])
    manifest = json.loads(result["assets/manifest.json"])
    original_manifest_hash = sha(source_files[GENERATED + "manifest.json"])
    bundle_id = manifest["bundle_id"] + "-workbuddy"
    for topic in index["topics"]:
        topic["path"] = PurePosixPath(mapped_path(GENERATED + topic["path"])).name
        if "sha256" in topic:
            topic["sha256"] = sha(result["assets/" + topic["path"]])
    index["bundle_id"] = bundle_id
    result["assets/index.json"] = (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode()
    entries = []
    for name, data in sorted(result.items()):
        if name.startswith("assets/") and name != "assets/manifest.json":
            entries.append({"path": name.split("/", 1)[1], "size": len(data), "sha256": sha(data)})
    manifest.update(bundle_id=bundle_id, files=entries, content_sha256=corpus_hash(entries))
    manifest["release_id"] += "-workbuddy"
    result["assets/manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    channel = json.loads(result["references/switch__release-channel.json"])
    channel.update(bundle_id=bundle_id, enabled=False, channel_url="")
    result["references/switch__release-channel.json"] = (json.dumps(channel, indent=2) + "\n").encode()
    schema = json.loads(result["references/contracts__workflow-registry.schema.json"])
    schema["$defs"]["workflow"]["properties"]["leaf"]["pattern"] = r"^references/workflows__[a-z-]+\.md$"
    result["references/contracts__workflow-registry.schema.json"] = (json.dumps(schema, indent=2) + "\n").encode()
    original = result["SKILL.md"].decode("utf-8-sig").replace("\r\n", "\n")
    if not original.startswith("---\n") or "\n---\n" not in original[4:]:
        raise PackageError("Unexpected source frontmatter")
    body = original.split("\n---\n", 1)[1]
    body = re.sub(r"\(currently `v?\d+\.\d+\.\d+`\)", "(see root `VERSION`)", body)
    yaml = ["---"]
    for key in ("name", "display_name", "display_name_en", "description", "description_zh", "description_en", "version", "author", "compatibility", "license"):
        if info.get(key):
            yaml.append(key + ": " + json.dumps(info[key], ensure_ascii=False))
    yaml.append("metadata:")
    for key in ("repository", "support_url"):
        if info.get(key):
            yaml.append("  " + key + ": " + json.dumps(info[key], ensure_ascii=False))
    yaml.append('  packaging: "workbuddy-flat-v1"')
    yaml.append("---")
    if preview:
        body = "\n> PREVIEW：团队发布信息尚待确认，本包仅用于本地检查，不代表正式版本或平台认证通过。\n" + body
    result["SKILL.md"] = ("\n".join(yaml) + "\n" + body).encode("utf-8")
    audit = {
        "path_mapping": adapter.mapping,
        "original_corpus_manifest_sha256": original_manifest_hash,
        "adapted_corpus_manifest_sha256": sha(result["assets/manifest.json"]),
        "notes": ["Python paths are patched at AST source locations; original f-strings and unaffected comments are preserved.",
                  "Flat corpus has a separate bundle ID and cache namespace; original nested release channel is disabled."],
    }
    return result, audit


def validate_layout(files: dict[str, bytes]) -> None:
    if "SKILL.md" not in files:
        raise PackageError("SKILL.md must be at the ZIP root")
    for name, data in files.items():
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or "\\" in name or len(p.parts) > 2:
            raise PackageError(f"Invalid upload path: {name}")
        if name.endswith(".py"):
            ast.parse(data.decode("utf-8"), filename=name)
        elif name.endswith(".json"):
            json.loads(data)
        elif name.endswith(".md"):
            for link in re.findall(r"\]\(([^)]+)\)", data.decode("utf-8")):
                if "://" in link or link.startswith(("#", "mailto:")):
                    continue
                target = posixpath.normpath(posixpath.join(str(p.parent), link.split("#")[0]))
                if target not in files and not any(x.startswith(target.rstrip("/") + "/") for x in files):
                    raise PackageError(f"Broken packaged link: {name} -> {link}")


def smoke(zip_path: Path) -> list[dict]:
    records = []
    with tempfile.TemporaryDirectory(prefix="ma2wb-check-") as directory:
        base = Path(directory).resolve()
        package = base / "installed" / "mindplus-agent-skill"
        package.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as archive:
            for item in archive.infolist():
                target = package.joinpath(*PurePosixPath(item.filename).parts).resolve()
                if not target.is_relative_to(package) or len(PurePosixPath(item.filename).parts) > 2:
                    raise PackageError("Unsafe ZIP member during validation")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
        environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", GITEE_TOKEN_FILE=str(base / "missing-token"))
        for key in ("GITEE_TOKEN", "GITEE_ACCESS_TOKEN", "MP_RELEASE_TOKEN", "PYTHONPATH"):
            environment.pop(key, None)

        def run(script: str, *args: str, codes=(0,)):
            completed = subprocess.run([sys.executable, "-B", str(package / script), *map(str, args)], cwd=base,
                                       env=environment, capture_output=True, encoding="utf-8", timeout=30)
            if completed.returncode not in codes:
                raise PackageError(f"Isolated check failed: {script} {args}\n{completed.stdout}\n{completed.stderr}")
            records.append({"script": script, "arguments": list(map(str, args)), "exit_code": completed.returncode})
            return json.loads(completed.stdout) if completed.stdout.lstrip().startswith("{") else None

        for path in sorted((package / "scripts").glob("*.py")):
            run("scripts/" + path.name, "--help")
        state = run("scripts/switch__check_reference_release.py", "--offline", "--cache-root", base / "cache")
        if Path(state["active_root"]) != package / "assets":
            raise PackageError("Offline reference check did not select packaged assets")
        for mode in ("UPLOAD", "PYTHON_BLOCK"):
            spec = base / (mode + "-spec.json")
            write_json(spec, {"schema_version": "mindplus-agent.extension-spec/v1", "identity": {"id": "demo", "author": "tester", "version": "1.0.0", "compatibility_id": "tester-demo-thirdex"},
                              "mode": mode, "blocks": [{"opcode": "hello", "block_type": "COMMAND", "message_id": "gui.blocklyText.demo.hello", "parameters": [], "generator_claim": "generator.addCode(...)"}],
                              "dependencies": [], "devices": [], "assets": [], "style": {"color1": "#00B0F0"}, "readme_claims": []})
            inventory = base / (mode + "-inventory.json")
            run("scripts/switch__spec_to_inventory.py", "--spec", spec, "--output", inventory)
            selection = run("scripts/switch__select_reference_topics.py", "--inventory", inventory, "--active-root", package / "assets", "--mode", mode)
            if not selection["topics"] or any(not Path(x["path"]).is_file() for x in selection["topics"]):
                raise PackageError("Selected reference topics do not resolve")
        project = base / "project"
        project.mkdir()
        (project / "config.json").write_text("{}")
        for goals in ("REVIEW", "PUBLISH"):
            args = ["start", "--goals", goals, "--project-root", project, "--work-root", base]
            if goals == "PUBLISH":
                args += ["--auth", "commit", "--auth", "push"]
            route = run("scripts/mpa.py", *args)
            if not Path(route["leaf_reference"]).is_file():
                raise PackageError("Route points at a missing flattened workflow")
        blocked = run("scripts/prepare_gitee_publish.py", "--project-root", base / "does-not-exist", codes=(3,))
        if blocked.get("reason_code") != "AUTH.GITEE_TOKEN_MISSING":
            raise PackageError("Missing token gate did not stop publication first")
    return records


def marketplace_copy(info: dict) -> str:
    """Local copy/paste artifact, not undocumented WorkBuddy frontmatter fields."""
    introduction = info.get("marketplace_introduction", info["description_zh"]).strip()
    prompts = [line.strip() for line in info.get("marketplace_prompts", "").splitlines() if line.strip()]
    return ("# WorkBuddy 市场文案\n\n"
            "以下内容用于市场后台填写。官方技能文档尚未说明这两个栏目的 ZIP 自动导入字段；本文件不进入技能 ZIP。\n\n"
            f"展示名称：{info.get('display_name', info['name'])}\n\n版本：{info['version']}\n\n"
            f"## 介绍\n\n{introduction}\n\n## 试试这样问我\n\n" +
            ("\n".join("- " + line for line in prompts) if prompts else "请在 release-info.json 中填写 marketplace_prompts，每行一条示例提问。") + "\n")


def build(source: Path, metadata: Path, output: Path, preview: bool) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or (output.is_relative_to(source) and not output.is_relative_to(source / "dist")):
        raise PackageError("Output must be outside the source skill or inside its ignored dist directory")
    info = load_metadata(metadata, preview)
    originals = collect(source)
    source_version = originals.get("VERSION", b"").decode("utf-8-sig").strip().lstrip("v")
    if source_version != info["version"]:
        raise PackageError("release-info.json version must match the source VERSION file")
    verify_source_corpus(originals)
    files, audit = build_files(originals, info, preview)
    validate_layout(files)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = output / (("preview-" if preview else "release-") + stamp)
    folder.mkdir()
    marketplace_path = folder / "marketplace-info.md"
    marketplace_path.write_text(marketplace_copy(info), encoding="utf-8")
    package = folder / "unpacked"
    package.mkdir()
    for name, data in files.items():
        target = package.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    zip_path = folder / (info["name"] + "-" + info["version"] + ("-preview" if preview else "") + "-workbuddy.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    report = {"status": "PENDING", "preview": preview, "source": str(source), "zip": str(zip_path), "file_count": len(files),
              "max_directory_depth": max(len(PurePosixPath(x).parts) - 1 for x in files), "metadata": info, **audit,
              "source_files": {name: sha(data) for name, data in originals.items()},
              "package_files": {name: sha(data) for name, data in files.items()}}
    report_path = folder / "build-report.json"
    try:
        report["checks"] = smoke(zip_path)
        after = collect(source)
        if {name: sha(data) for name, data in after.items()} != report["source_files"]:
            raise PackageError("Source changed during packaging; rerun from a stable source")
        report.update(status="PASS", zip_sha256=sha(zip_path.read_bytes()), certification="NOT_SUBMITTED")
    except Exception as exc:
        report.update(status="FAIL", error=str(exc))
        write_json(report_path, report)
        raise PackageError(f"Package checks failed; do not upload. Report: {report_path}\n{exc}") from exc
    write_json(report_path, report)
    return {"status": "PASS", "preview": preview, "zip": str(zip_path), "unpacked": str(package), "report": str(report_path), "marketplace_info": str(marketplace_path),
            "file_count": len(files), "checks": len(report["checks"]), "zip_sha256": report["zip_sha256"], "certification": "NOT_SUBMITTED"}


class ReleaseAPI:
    def __init__(self, repository: str, token: str):
        match = re.fullmatch(r"https://gitee\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?", repository)
        if not match:
            raise PackageError("repository must be an HTTPS Gitee repository URL")
        self.base = "https://gitee.com/api/v5/repos/" + "/".join(match.groups())
        self.token = token

    def request(self, method: str, path: str, payload=None, attachment: Path | None = None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        data = None
        if attachment is not None:
            boundary = "mindplus" + uuid.uuid4().hex
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{attachment.name}"\r\n'
                    'Content-Type: application/zip\r\n\r\n').encode() + attachment.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None  # Never forward the API credential to another endpoint.

        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if method == "GET" and exc.code == 404:
                return None
            raise PackageError(f"Gitee {method} {path} failed: HTTP {exc.code}; rerun to reconcile partial publication") from None
        except (OSError, ValueError):
            raise PackageError(f"Gitee {method} {path} unavailable; rerun to reconcile partial publication") from None

    def attachments(self, release_id):
        items = []
        for page in range(1, 101):
            batch = self.request("GET", f"/releases/{release_id}/attach_files?page={page}&per_page=100")
            if not isinstance(batch, list):
                raise PackageError("Invalid Gitee attachment list")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise PackageError("Too many Release attachments")

    def verify_attachment(self, asset: dict, expected_sha: str):
        url = asset.get("browser_download_url", "")
        if not url.startswith("https://"):
            raise PackageError("Attachment has no HTTPS download URL")
        try:
            # Public attachment downloads deliberately carry no API credential.
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024 or sha(data) != expected_sha:
                raise PackageError("Release attachment bytes differ; existing files are never overwritten")
        except OSError:
            raise PackageError("Cannot verify Release attachment download") from None


def release_body(existing: str, info: dict, tag: str, digest: str, filename: str) -> str:
    start, end = "<!-- mindplus-pack:start -->", "<!-- mindplus-pack:end -->"
    repo = info["repository"].rstrip("/")
    block = (f"{start}\n"
             f"- WorkBuddy：[下载兼容 ZIP]({repo}/releases/download/{tag}/{filename})\n"
             f"- 其他 Agent：[下载通用源码 ZIP]({repo}/archive/refs/tags/{tag}.zip)\n"
             f"- 版本：`{info['version']}`\n- WB SHA-256：`{digest}`\n{end}")
    if start in existing or end in existing:
        if existing.count(start) != 1 or existing.count(end) != 1 or existing.index(start) > existing.index(end):
            raise PackageError("Malformed automatic Release section; preserve it for manual correction")
        a, b = existing.index(start), existing.index(end) + len(end)
        return existing[:a] + block + existing[b:]
    return existing + ("\n\n" if existing else "") + block


def release_commit(source: Path, info: dict, tag: str) -> str:
    if tag not in (info["version"], "v" + info["version"]):
        raise PackageError("Release tag must match VERSION and release-info.json")

    def git(*args):
        result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, encoding="utf-8", timeout=45,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never"))
        if result.returncode:
            raise PackageError("Git release check failed: verify checkout, tag and remote access")
        return result.stdout.strip()

    if git("status", "--porcelain", "--untracked-files=all"):
        raise PackageError("Release publishing requires a clean committed checkout")
    head = git("rev-parse", "HEAD")
    if git("rev-parse", "refs/tags/" + tag + "^{commit}") != head:
        raise PackageError("Release tag does not point to the checkout HEAD")
    refs = git("ls-remote", "--tags", info["repository"].rstrip("/") + ".git", "refs/tags/" + tag, "refs/tags/" + tag + "^{}")
    entries = dict(line.split()[::-1] for line in refs.splitlines())
    remote = entries.get("refs/tags/" + tag + "^{}", entries.get("refs/tags/" + tag))
    if remote != head:
        raise PackageError("Remote tag does not match the built commit")
    return head


def release_token() -> str:
    """Read a CI secret or the local Windows Credential Manager secret."""
    value = os.environ.get("MP_RELEASE_TOKEN", "").strip()
    if value and ("\n" in value or "\r" in value or len(value) > 256):
        raise PackageError("Invalid MP_RELEASE_TOKEN format")
    if value:
        return value
    source, token = resolve_windows_credential()
    if source:
        return token
    raise PackageError("Configure MP_RELEASE_TOKEN in Gitee Go or save the PAT as the password for git:https://gitee.com in Windows Credential Manager")


def publish(result: dict, source: Path, metadata: Path, tag: str) -> dict:
    if result.get("status") != "PASS" or result.get("preview"):
        raise PackageError("Only a passing non-preview build may be published")
    token = release_token()
    info = load_metadata(metadata, False)
    api = ReleaseAPI(info["repository"], token)
    if (source / "VERSION").read_text(encoding="utf-8-sig").strip() != info["version"]:
        raise PackageError("Source version changed after building")
    archive = Path(result["zip"])
    if archive.name != f"{info['name']}-{info['version']}-workbuddy.zip" or sha(archive.read_bytes()) != result["zip_sha256"]:
        raise PackageError("Built archive changed before publication")
    report = read_json(Path(result["report"]))
    if {name: sha(data) for name, data in collect(source).items()} != report["source_files"] or info != report["metadata"]:
        raise PackageError("Source or metadata changed after building")
    commit = release_commit(source, info, tag)
    path = "/releases/tags/" + urllib.parse.quote(tag, safe="")
    release = api.request("GET", path)
    if release is None:
        release = api.request("POST", "/releases", {"tag_name": tag, "target_commitish": commit,
                              "name": "v" + info["version"], "body": info["description_zh"], "prerelease": False})
    if release.get("tag_name") != tag or release.get("prerelease"):
        raise PackageError("Existing Release tag or prerelease status is incompatible")
    release_id = release["id"]
    matches = [item for item in api.attachments(release_id) if item.get("name") == archive.name]
    if len(matches) > 1:
        raise PackageError("Duplicate same-name Release attachments; resolve manually")
    asset = matches[0] if matches else api.request("POST", f"/releases/{release_id}/attach_files", attachment=archive)
    api.verify_attachment(asset, result["zip_sha256"])
    # Re-read after upload so intervening human edits are preserved where possible.
    release = api.request("GET", path)
    body = release_body(release.get("body") or "", info, tag, result["zip_sha256"], archive.name)
    if body != (release.get("body") or ""):
        api.request("PATCH", f"/releases/{release_id}", {"tag_name": tag, "name": release["name"],
                    "body": body, "prerelease": release.get("prerelease", False)})
    verified = api.request("GET", path)
    if verified.get("body") != body:
        raise PackageError("Release body verification failed; inspect concurrent edits before retrying")
    return {"status": "PASS", "release": info["repository"].rstrip("/") + "/releases/" + tag,
            "attachment": archive.name, "reused_attachment": bool(matches), "commit": commit}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent)
    parser.add_argument("--metadata", type=Path, default=HERE.parent / "release-info.json")
    parser.add_argument("--output-dir", type=Path, default=HERE.parent / "dist")
    parser.add_argument("--preview", action="store_true", help="allow incomplete team metadata; mark the package as a preview")
    parser.add_argument("--publish", action="store_true", help="upload the passing build and update its Gitee Release")
    parser.add_argument("--tag", help="existing remote version tag, required with --publish")
    args = parser.parse_args()
    try:
        if args.publish and (args.preview or not args.tag):
            raise PackageError("--publish requires --tag and cannot be combined with --preview")
        if args.publish:
            release_token()
        result = build(args.source, args.metadata, args.output_dir, args.preview)
        if args.publish:
            result["publication"] = publish(result, args.source.resolve(), args.metadata, args.tag)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PackageError, OSError, ValueError, KeyError, SyntaxError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
