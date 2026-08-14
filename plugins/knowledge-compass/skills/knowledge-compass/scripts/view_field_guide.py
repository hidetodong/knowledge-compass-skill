#!/usr/bin/env python3
"""Render a knowledge-compass field guide (JSON) into a self-contained interactive HTML page,
archive it into a central library, and (when local) open it in the browser.

The data model is JSON (schema documented in SKILL.md and below): a topic, the fragments it was
reverse-inferred from, a domain judgment + confidence, the disciplines it spans, an overview,
prerequisites, layered sources (each carrying priority / prereq / difficulty / audience /
verification), and a staged plan. The JSON is the single source of truth — this script only
renders it, so re-run after editing the JSON to refresh both the page and the library.

It embeds the data into assets/viewer_template.html, writes a self-contained <name>.html, keeps
the .json (source) beside it, copies both into a central library (default ~/knowledge-compass/,
override with --library or $KNOWLEDGE_COMPASS_LIBRARY), and rebuilds the library's index.html —
the "open one page, click through your past guides" view. Point the library at a cloud-synced
folder for free cloud archival + cross-device re-viewing.

The library is the products directory: HTML, JSON and index.html all live there together. If the
input .json already lives inside the library, it is rendered IN PLACE (the .html is written
beside it under the same name, the .json is rewritten in place) — no date-stamped copy is minted,
so that one .json stays the single source of truth and editing + re-running is idempotent (no
duplicate "one guide, two JSONs" scatter, even across days). A .json from outside the library is
archived under <date>-<topic-slug> on first render; thereafter edit the in-library copy and re-run
it. --out always wins when given. --no-archive guarantees that neither output file is inside the
configured library; when the input already lives there, provide --out with an external path.

Usage:
    python3 view_field_guide.py guide.json [--out PATH] [--library DIR]
                                [--no-archive] [--no-open]
    cat guide.json | python3 view_field_guide.py        # read JSON from stdin

The JSON schema (all fields optional except topic + layers):
{
  "topic": "概率论 · 极限定理",
  "domain": "数学 · 概率论",                      # （可选）领域眉题：反推出的领域+分支，渲染成大标题上方的金色 kicker
  "fragments": ["泊松定律", "大数定律"],          # 用户给的原始碎片，hero 里平铺展示
  "domain_judgment": "一句话——哪些碎片共现、锁定了哪个领域",
  "confidence": "高",                            # 高 / 中 / 低，hero 里显示为置信度
  "excluded": "（可选）被排除的候选 / 不吻合的词；全部吻合则省略",
  "disciplines": ["数学 · 概率论", "数理统计"],   # 领域横跨的学科门类
  "overview": "2-4 句领域速览",
  "prerequisites": "学这个领域整体需要的前置知识（如 微积分），显示为独立小卡片",
  "layers": [
    {"emoji": "🌱", "title": "入门", "subtitle": "建立直觉 / 打基础",
     "resources": [
       {"name": "《概率导论》（Introduction to Probability）", "meta": "作者，版本/年份",
        "id": "intro-prob",          # （可选）1-64 位小写 ASCII 稳定键，供 requires 引用
        "type": "教材",
        "priority": "必读",          # 必读 | 推荐 | 可选 —— 决定徽章+左边框色，必读自动排前
        "prereq": "微积分",          # 读这一本需要的前置背景知识（自由文本，与 requires 不同）
        "requires": ["calculus"],    # （可选）作为前置的其他资源 id 数组，驱动「学习路线树」
        "reason": "为什么权威 / 为什么在这一层",
        "difficulty": "入门友好",
        "audience": "想系统自学的零基础者",
        "url": "https://...",
        "free": true,
        "verified": true,            # 反幻觉：只有联网核实通过才设 true；缺失/存疑均视为未核实
        "verify_note": "未核实原因"}  # verified=false 时，hover 显示的说明
     ]}
  ],
  # 学习路径优先用 plan（分阶段、可勾选、进度记忆）；没有 plan 时才退回 route（一段话）。
  "plan": [
    {"step": "阶段 1 · 建立直觉（约 2-3 周）",
     "detail": "读哪些资源的哪部分、目标是什么、达到什么标志可进入下一阶段"}
  ],
  "route": "（可选，plan 的简短替代）2-4 句可执行的建议顺序",
  # 参考来源：本指南分析所依据的可溯出处。正文里写 [1][2] 角标即按序号链到底部编号列表。
  "references": [
    {"title": "《自杀论》（Le Suicide）", "source": "涂尔干 · 1897",
     "url": "https://...", "note": "（可选）补充说明"}
  ]
}

Stdlib only. Compatible with Python 3.8+.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import webbrowser
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

ASSETS = Path(__file__).resolve().parent.parent / "assets"
VIEWER_TEMPLATE = ASSETS / "viewer_template.html"
INDEX_TEMPLATE = ASSETS / "index_template.html"
VIEWER_PLACEHOLDER = "/*__PATH_DATA__*/"
INDEX_PLACEHOLDER = "__LIBRARY_DATA__"

# Central archive library. Override per-run with --library, or persistently via env var.
# Point this at a cloud-synced folder (e.g. a Google Drive for desktop sync dir) to get
# automatic cloud archival + cross-device re-viewing for free.
DEFAULT_LIBRARY = Path(os.environ.get("KNOWLEDGE_COMPASS_LIBRARY", "~/knowledge-compass")).expanduser()
RESOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
RESERVED_RESOURCE_IDS = {"__proto__", "prototype", "constructor"}
HTTP_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
FORBIDDEN_AUTHORITY_CHARS = frozenset('<>"`{}|^')


def is_valid_web_hostname(value):
    """Validate the conservative hostname grammar shared with the browser viewer."""
    if not value or "%" in value:
        return False
    hostname = value[:-1] if value.endswith(".") else value
    if not hostname or len(hostname) > 253:
        return False
    labels = hostname.split(".")
    if any(not label or len(label) > 63 for label in labels):
        return False

    if all(char.isascii() and (char.isdigit() or char == ".") for char in hostname):
        if len(labels) != 4:
            return False
        return all(
            label.isascii()
            and label.isdigit()
            and (label == "0" or not label.startswith("0"))
            and int(label) <= 255
            for label in labels
        )

    return all(
        char in {"-", "_"} or unicodedata.category(char)[0] in {"L", "M", "N"}
        for label in labels
        for char in label
    )


def is_safe_web_url(value):
    """Return True only for absolute HTTP(S) URLs."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(unicodedata.category(char) in {"Cc", "Cs"} for char in value)
    ):
        return False
    trimmed = value.strip()
    # Keep the browser and Python trust boundaries deterministic. urllib accepts
    # whitespace inside a hostname while WHATWG URL parsing rejects it, which can
    # otherwise produce a Python-generated page that refuses its own embedded data.
    if any(char.isspace() or char == "\\" or char == "\ufeff" for char in trimmed):
        return False
    scheme = HTTP_SCHEME_RE.match(trimmed)
    if scheme is None:
        return False
    remainder = trimmed[scheme.end() :]
    authority = re.split(r"[/?#]", remainder, maxsplit=1)[0]
    if not authority or any(char in FORBIDDEN_AUTHORITY_CHARS for char in authority):
        return False
    host_port = authority.rsplit("@", 1)[-1]
    if not host_port:
        return False

    if host_port.startswith("["):
        close = host_port.find("]")
        if close <= 1:
            return False
        hostname = host_port[1:close]
        if "%" in hostname:
            return False
        tail = host_port[close + 1 :]
        try:
            ipaddress.IPv6Address(hostname)
        except ipaddress.AddressValueError:
            return False
        if not tail:
            return True
        if not tail.startswith(":"):
            return False
        port = tail[1:]
    else:
        if ":" in host_port:
            hostname, separator, port = host_port.rpartition(":")
            if not separator or ":" in hostname:
                return False
        else:
            hostname, port = host_port, None
        if not is_valid_web_hostname(hostname):
            return False

    return port is None or (
        port.isascii() and port.isdigit() and int(port) <= 65535
    )


def is_valid_resource_id(value):
    return (
        isinstance(value, str)
        and RESOURCE_ID_RE.fullmatch(value) is not None
        and value not in RESERVED_RESOURCE_IDS
    )


def is_within(path, directory):
    """Return whether path resolves inside directory (including directory itself)."""
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False
    except (OSError, RuntimeError):
        return True  # Fail closed when a symlink loop or resolution error hides the boundary.


def validate_guide(data):
    """Return human-readable schema errors for a field-guide payload."""
    errors = []
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]

    topic = data.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        errors.append("topic must be a non-empty string")
    elif any(unicodedata.category(char) in {"Cc", "Cs"} for char in topic):
        errors.append("topic must not contain control characters")

    for key in (
        "domain",
        "domain_judgment",
        "confidence",
        "excluded",
        "overview",
        "prerequisites",
        "route",
    ):
        if key in data and not isinstance(data.get(key), str):
            errors.append(f"{key} must be a string")

    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        errors.append("layers must be a non-empty array")
        return errors

    resource_ids = {}
    dependencies = []
    for layer_index, layer in enumerate(layers):
        layer_path = f"layers[{layer_index}]"
        if not isinstance(layer, dict):
            errors.append(f"{layer_path} must be an object")
            continue
        for key in ("emoji", "title", "subtitle"):
            if key in layer and not isinstance(layer.get(key), str):
                errors.append(f"{layer_path}.{key} must be a string")
        resources = layer.get("resources")
        if not isinstance(resources, list):
            errors.append(f"{layer_path}.resources must be an array")
            continue
        for resource_index, resource in enumerate(resources):
            resource_path = f"{layer_path}.resources[{resource_index}]"
            if not isinstance(resource, dict):
                errors.append(f"{resource_path} must be an object")
                continue
            if "url" in resource and not is_safe_web_url(resource.get("url")):
                errors.append(f"{resource_path}.url must be an absolute http(s) URL")
            if "verified" in resource and not isinstance(resource.get("verified"), bool):
                errors.append(f"{resource_path}.verified must be true or false")
            if "free" in resource and not isinstance(resource.get("free"), bool):
                errors.append(f"{resource_path}.free must be true or false")
            for key in (
                "name",
                "meta",
                "type",
                "priority",
                "prereq",
                "reason",
                "difficulty",
                "audience",
                "verify_note",
            ):
                if key in resource and not isinstance(resource.get(key), str):
                    errors.append(f"{resource_path}.{key} must be a string")
            if resource.get("priority") not in (None, "必读", "推荐", "可选"):
                errors.append(f"{resource_path}.priority must be 必读, 推荐, or 可选")

            resource_id = resource.get("id")
            resource_id_valid = resource_id is None
            if resource_id is not None:
                if not is_valid_resource_id(resource_id):
                    errors.append(
                        f"{resource_path}.id must use 1-64 lowercase letters, digits, '.', '_' or '-' "
                        "and must not be a reserved object key"
                    )
                elif resource_id in resource_ids:
                    errors.append(
                        f"{resource_path}.id duplicates {resource_ids[resource_id]}: {resource_id}"
                    )
                else:
                    resource_ids[resource_id] = f"{resource_path}.id"
                    resource_id_valid = True

            requires = resource.get("requires", [])
            if not isinstance(requires, list) or any(
                not is_valid_resource_id(item) for item in requires
            ):
                errors.append(
                    f"{resource_path}.requires must be an array of valid, non-reserved resource ids"
                )
            elif resource_id_valid and isinstance(resource_id, str):
                dependencies.append((resource_id, requires, resource_path))
            elif requires:
                errors.append(f"{resource_path}.id is required when requires is non-empty")

    for resource_id, requires, resource_path in dependencies:
        for required_id in requires:
            if required_id == resource_id:
                errors.append(f"{resource_path}.requires cannot reference itself: {resource_id}")
            elif required_id not in resource_ids:
                errors.append(f"{resource_path}.requires references unknown id: {required_id}")

    dependency_map = {resource_id: requires for resource_id, requires, _ in dependencies}
    visiting = set()
    visited = set()

    def visit(resource_id, trail):
        if resource_id in visiting:
            cycle = " -> ".join(trail + [resource_id])
            errors.append(f"requires contains a cycle: {cycle}")
            return
        if resource_id in visited:
            return
        visiting.add(resource_id)
        for required_id in dependency_map.get(resource_id, []):
            if required_id in dependency_map:
                visit(required_id, trail + [resource_id])
        visiting.remove(resource_id)
        visited.add(resource_id)

    for resource_id in dependency_map:
        visit(resource_id, [])

    references = data.get("references", [])
    if not isinstance(references, list):
        errors.append("references must be an array")
    else:
        for index, reference in enumerate(references):
            path = f"references[{index}]"
            if not isinstance(reference, dict):
                errors.append(f"{path} must be an object")
            else:
                if "url" in reference and not is_safe_web_url(reference.get("url")):
                    errors.append(f"{path}.url must be an absolute http(s) URL")
                for key in ("title", "name", "source", "note"):
                    if key in reference and not isinstance(reference.get(key), str):
                        errors.append(f"{path}.{key} must be a string")

    plan = data.get("plan", [])
    if not isinstance(plan, list):
        errors.append("plan must be an array")
    else:
        for index, step in enumerate(plan):
            if not isinstance(step, dict):
                errors.append(f"plan[{index}] must be an object")
            else:
                for key in ("step", "title", "detail"):
                    if key in step and not isinstance(step.get(key), str):
                        errors.append(f"plan[{index}].{key} must be a string")

    for key in ("fragments", "disciplines"):
        value = data.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"{key} must be an array of strings")

    return errors


def slugify(text):
    """A filesystem-friendly slug; keeps CJK, drops punctuation/whitespace."""
    text = (text or "field-guide").strip()
    text = "".join(
        char for char in text if unicodedata.category(char) not in {"Cc", "Cs"}
    )
    text = re.sub(r"[\\/:*?\"<>|·・,，。、\s]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    # Leave ample room for the date prefix, numeric collision suffix and extension
    # under common 255-byte filesystem limits without splitting a UTF-8 sequence.
    text = text.encode("utf-8")[:160].decode("utf-8", errors="ignore").strip("-.")
    return text or "field-guide"


def validate_destination(path):
    """Reject destinations that could redirect writes or are not regular files."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"refusing to write through symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"destination is not a regular file: {path}")


def write_text_atomic(path, content):
    """Atomically replace a regular file without following a destination symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_destination(path)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path = Path(handle.name)
        os.replace(str(tmp_path), str(path))
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def copy_file_atomic(source, destination):
    """Copy a file through a temporary sibling, then atomically publish it."""
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_destination(destination)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(destination.parent),
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copystat(str(source), str(tmp_path), follow_symlinks=False)
        os.replace(str(tmp_path), str(destination))
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def inline(template_path, placeholder, payload_obj):
    """Embed JSON into a script block without allowing HTML parser breakouts."""
    tpl = Path(template_path).read_text(encoding="utf-8")
    payload = json.dumps(payload_obj, ensure_ascii=False)
    # HTML end tags are case-insensitive. Escaping every raw '<' protects mixed-case
    # variants such as </ScRiPt>; the other replacements keep the payload inert in HTML.
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    placeholder_count = tpl.count(placeholder)
    if placeholder_count != 1:
        raise ValueError(
            f"placeholder {placeholder} must appear exactly once in {template_path}; "
            f"found {placeholder_count}"
        )
    return tpl.replace(placeholder, payload, 1)


def index_entry(data, html_name, mtime):
    sources = [r for layer in data.get("layers", []) for r in layer.get("resources", [])]
    return {
        "topic": data.get("topic", "") or "领域指南",
        "domain": data.get("domain", "") or "",
        "confidence": data.get("confidence", ""),
        "disciplines": data.get("disciplines", []) or [],
        # Encode every filename byte so even an unusual name beginning with
        # "javascript:" remains a relative file link in the generated index.
        "html": quote(html_name, safe=""),
        "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
        "_mtime": mtime,
        "sources": len(sources),
        "unverified": sum(1 for r in sources if r.get("verified") is not True),
    }


def build_index(library):
    """Scan the library's *.json guides and (re)write index.html — the click-through entry page."""
    entries = []
    for jf in sorted(library.glob("*.json")):
        html_file = jf.with_suffix(".html")
        if jf.is_symlink() or html_file.is_symlink() or not html_file.is_file():
            continue                      # only list guides that have a viewable page
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if validate_guide(data):
            continue
        entries.append(index_entry(data, html_file.name, jf.stat().st_mtime))
    entries.sort(key=lambda e: e["_mtime"], reverse=True)   # newest first
    for e in entries:
        e.pop("_mtime", None)
    index_path = library / "index.html"
    write_text_atomic(index_path, inline(INDEX_TEMPLATE, INDEX_PLACEHOLDER, entries))
    return index_path, len(entries)


def next_available_pair(html_path):
    """Avoid silently overwriting an unrelated HTML/JSON pair."""
    html_path = Path(html_path)
    if not (html_path.exists() or html_path.is_symlink()) and not (
        html_path.with_suffix(".json").exists() or html_path.with_suffix(".json").is_symlink()
    ):
        return html_path
    for suffix in range(2, 10000):
        candidate = html_path.with_name(f"{html_path.stem}-{suffix}{html_path.suffix}")
        if not (candidate.exists() or candidate.is_symlink()) and not (
            candidate.with_suffix(".json").exists()
            or candidate.with_suffix(".json").is_symlink()
        ):
            return candidate
    raise RuntimeError(f"could not allocate a unique output name beside {html_path}")


def is_remote():
    """Heuristic: under SSH/mosh there's no local browser worth opening."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY") or os.environ.get("SSH_CLIENT"):
        return True
    # macOS `open` works without DISPLAY, so only treat *Linux without a display* as remote.
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def open_local(path):
    """Try to open the file in the local browser. Return True if attempted."""
    uri = path.resolve().as_uri()
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
            return True
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        return webbrowser.open(uri)
    except Exception:
        try:
            return webbrowser.open(uri)
        except Exception:
            return False


def main():
    ap = argparse.ArgumentParser(description="Render + archive a knowledge-compass field guide (JSON).")
    ap.add_argument("data", nargs="?", help="path to the field-guide .json (omit to read JSON from stdin)")
    ap.add_argument("--out", help="output .html path (owns/replaces the sibling .json pair; must end in .html)")
    ap.add_argument("--library", help=f"central archive dir (default: $KNOWLEDGE_COMPASS_LIBRARY or {DEFAULT_LIBRARY})")
    ap.add_argument("--no-archive", action="store_true", help="don't touch the central library; write beside an external input, or use --out outside the library")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser; just write + print the path")
    args = ap.parse_args()

    # Load data
    try:
        raw = Path(args.data).read_text(encoding="utf-8") if args.data else sys.stdin.read()
        data = json.loads(raw)
    except FileNotFoundError:
        print(f"error: data file not found: {args.data}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as error:
        print(f"error: could not read field-guide data: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 2

    schema_errors = validate_guide(data)
    if schema_errors:
        print("error: invalid field-guide data:", file=sys.stderr)
        for error in schema_errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    if not VIEWER_TEMPLATE.is_file():
        print(f"error: viewer template missing: {VIEWER_TEMPLATE}", file=sys.stderr)
        return 2

    library = Path(args.library).expanduser() if args.library else DEFAULT_LIBRARY

    # Resolve output path:
    #   --out             → honored verbatim.
    #   input in library  → render IN PLACE beside the input, reusing its name. The input .json
    #                       is itself the single source of truth, so no date-stamped copy is
    #                       minted — editing it and re-running stays idempotent (one JSON per
    #                       guide, no scatter, even across days).
    #   otherwise         → first-time archival: mint <date>-<topic-slug> in the library so the
    #                       guide lands in one place with a naturally-sorted name.
    data_path = Path(args.data).resolve() if args.data else None
    in_library = data_path is not None and data_path.parent == library.expanduser().resolve()
    try:
        if args.out:
            out = Path(args.out).expanduser()
            if out.suffix.lower() != ".html":
                print("error: --out must end in .html", file=sys.stderr)
                return 2
        elif args.no_archive:
            if data_path is not None:
                out = data_path.with_suffix(".html")
            else:
                out = next_available_pair(Path.cwd() / f"{slugify(data.get('topic'))}.html")
        elif in_library:
            out = data_path.with_suffix(".html")
        else:
            out = next_available_pair(
                library / f"{date.today().isoformat()}-{slugify(data.get('topic'))}.html"
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: could not resolve output path: {error}", file=sys.stderr)
        return 2
    json_path = out.with_suffix(".json")
    if args.no_archive and (is_within(out, library) or is_within(json_path, library)):
        print(
            "error: --no-archive output must be outside the central library; use --out PATH",
            file=sys.stderr,
        )
        return 2
    if not args.no_archive and out.parent.resolve() == library.resolve() and out.name.lower() == "index.html":
        print("error: --out cannot replace the library index.html", file=sys.stderr)
        return 2

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        validate_destination(out)
        if data_path is None or json_path.resolve() != data_path.resolve():
            validate_destination(json_path)
        if not args.no_archive:
            library.mkdir(parents=True, exist_ok=True)
            validate_destination(library / "index.html")
        view_data = dict(data)
        view_data["_storage_key"] = hashlib.sha256(
            str(out.resolve()).encode("utf-8")
        ).hexdigest()[:24]
        write_text_atomic(out, inline(VIEWER_TEMPLATE, VIEWER_PLACEHOLDER, view_data))
        # Keep the JSON (source of truth) beside the HTML. If it is already the input,
        # leave the user's bytes untouched rather than rewriting through a possible symlink.
        if data_path is None or json_path.resolve() != data_path.resolve():
            write_text_atomic(json_path, json.dumps(data, ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: could not write field guide: {error}", file=sys.stderr)
        return 2
    abs_out = out.resolve()
    print(f"✅ 领域指南网页已生成：{abs_out}")

    if not args.no_archive:
        try:
            # If the output lives outside the library, drop a collision-safe copy in.
            if out.resolve().parent != library.resolve():
                archive_html = next_available_pair(library / out.name)
                archive_json = archive_html.with_suffix(".json")
                copy_file_atomic(out, archive_html)
                copy_file_atomic(json_path, archive_json)
            index_path, n = build_index(library)
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: could not archive field guide: {error}", file=sys.stderr)
            return 2
        print(f"   已归档到领域库：{library}")
        print(f"   领域库索引（{n} 份 · 打开它点卡片回看）：{index_path}")

    if args.no_open:
        print("   （--no-open：未自动打开）")
    elif is_remote():
        print("   检测到远程会话（SSH/mosh），未自动打开浏览器。")
        print(f"   在本机用浏览器打开： file://{abs_out}")
    else:
        opened = open_local(out)
        print("   已尝试在浏览器打开。" if opened else f"   未能自动打开，请手动打开： file://{abs_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
