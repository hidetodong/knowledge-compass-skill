#!/usr/bin/env python3
"""Validate the public Knowledge Compass plugin distribution.

This validator intentionally uses only the Python standard library so the same
command works in a fresh checkout on every supported Python version.
"""

from __future__ import print_function

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"
MARKETPLACE_NAME = "knowledge-compass-skill"
PLUGIN_NAME = "knowledge-compass"
PLUGIN_ROOT = REPO_ROOT / "plugins" / PLUGIN_NAME
SKILL_ROOT = PLUGIN_ROOT / "skills" / PLUGIN_NAME

CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CODEX_MARKETPLACE = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
CLAUDE_PLUGIN = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
CODEX_PLUGIN = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
SKILL_FILE = SKILL_ROOT / "SKILL.md"
OPENAI_YAML = SKILL_ROOT / "agents" / "openai.yaml"

PUBLIC_ROOTS = (
    REPO_ROOT / ".agents",
    REPO_ROOT / ".claude-plugin",
    REPO_ROOT / ".github",
    REPO_ROOT / "plugins",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests",
)
PUBLIC_FILES = (
    REPO_ROOT / ".gitignore",
    REPO_ROOT / "LICENSE",
    REPO_ROOT / "README.md",
)
LOCAL_ONLY_TRACKED_PATHS = {
    ".ai",
    ".claude",
    "AGENTS.md",
    "CLAUDE.md",
    "deliveries",
    "origin",
}


def load_json(path: Path, errors: List[str]) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        errors.append("missing required JSON file: {}".format(path.relative_to(REPO_ROOT)))
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append("invalid JSON in {}: {}".format(path.relative_to(REPO_ROOT), exc))
        return None
    if not isinstance(payload, dict):
        errors.append("{} must contain a JSON object".format(path.relative_to(REPO_ROOT)))
        return None
    return payload


def nested(payload: Optional[Dict[str, Any]], *keys: str) -> Any:
    value = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def one_plugin(
    payload: Optional[Dict[str, Any]], path: Path, errors: List[str]
) -> Optional[Dict[str, Any]]:
    plugins = nested(payload, "plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        errors.append("{} must declare exactly one plugin".format(path.relative_to(REPO_ROOT)))
        return None
    return plugins[0]


def frontmatter(text: str, errors: List[str]) -> str:
    if not text.startswith("---\n"):
        errors.append("SKILL.md must begin with YAML frontmatter")
        return ""
    end = text.find("\n---\n", 4)
    if end < 0:
        errors.append("SKILL.md frontmatter is not terminated")
        return ""
    return text[4:end]


def frontmatter_scalar(block: str, key: str) -> Optional[str]:
    match = re.search(r"^{}:\s*[\"']?([^\n\"']+?)[\"']?\s*$".format(re.escape(key)), block, re.MULTILINE)
    return match.group(1).strip() if match else None


def metadata_version(block: str) -> Optional[str]:
    match = re.search(
        r"^metadata:\s*\n(?:^[ \t]+[^\n]*\n)*?^[ \t]+version:\s*[\"']?([^\n\"']+)[\"']?\s*$",
        block,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def iter_public_files() -> Iterable[Path]:
    for path in PUBLIC_FILES:
        if path.is_file():
            yield path
    for root in PUBLIC_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                yield path


def tracked_files(errors: List[str]) -> List[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        errors.append("git ls-files failed while checking public repository hygiene")
        return []
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def validate() -> List[str]:
    errors = []  # type: List[str]

    claude_marketplace = load_json(CLAUDE_MARKETPLACE, errors)
    codex_marketplace = load_json(CODEX_MARKETPLACE, errors)
    claude_plugin = load_json(CLAUDE_PLUGIN, errors)
    codex_plugin = load_json(CODEX_PLUGIN, errors)

    claude_entry = one_plugin(claude_marketplace, CLAUDE_MARKETPLACE, errors)
    codex_entry = one_plugin(codex_marketplace, CODEX_MARKETPLACE, errors)

    if nested(claude_marketplace, "name") != MARKETPLACE_NAME:
        errors.append("Claude marketplace name must be {!r}".format(MARKETPLACE_NAME))
    if nested(codex_marketplace, "name") != MARKETPLACE_NAME:
        errors.append("Codex marketplace name must be {!r}".format(MARKETPLACE_NAME))
    if nested(claude_marketplace, "metadata", "version") != VERSION:
        errors.append("Claude marketplace metadata.version must be {}".format(VERSION))

    if claude_entry is not None:
        if claude_entry.get("name") != PLUGIN_NAME:
            errors.append("Claude marketplace plugin name must be {!r}".format(PLUGIN_NAME))
        if claude_entry.get("source") != "./plugins/knowledge-compass":
            errors.append("Claude marketplace must reference ./plugins/knowledge-compass")
        if claude_entry.get("version") != VERSION:
            errors.append("Claude marketplace plugin version must be {}".format(VERSION))

    if codex_entry is not None:
        if codex_entry.get("name") != PLUGIN_NAME:
            errors.append("Codex marketplace plugin name must be {!r}".format(PLUGIN_NAME))
        expected_source = {"source": "local", "path": "./plugins/knowledge-compass"}
        if codex_entry.get("source") != expected_source:
            errors.append("Codex marketplace must reference the canonical local plugin path")

    for label, manifest in (("Claude", claude_plugin), ("Codex", codex_plugin)):
        if nested(manifest, "name") != PLUGIN_NAME:
            errors.append("{} plugin name must be {!r}".format(label, PLUGIN_NAME))
        if nested(manifest, "version") != VERSION:
            errors.append("{} plugin version must be {}".format(label, VERSION))
        if nested(manifest, "license") != "MIT":
            errors.append("{} plugin license must be MIT".format(label))

    if nested(codex_plugin, "skills") != "./skills/":
        errors.append("Codex plugin must reference ./skills/")

    if not SKILL_FILE.is_file():
        errors.append("missing canonical skills/knowledge-compass/SKILL.md")
        skill_text = ""
    else:
        skill_text = SKILL_FILE.read_text(encoding="utf-8")
    block = frontmatter(skill_text, errors) if skill_text else ""
    if block:
        if frontmatter_scalar(block, "name") != PLUGIN_NAME:
            errors.append("SKILL.md name must be {!r}".format(PLUGIN_NAME))
        if frontmatter_scalar(block, "license") != "MIT":
            errors.append("SKILL.md license must be MIT")
        if metadata_version(block) != VERSION:
            errors.append("SKILL.md metadata.version must be {}".format(VERSION))

    skill_files = []
    plugins_root = REPO_ROOT / "plugins"
    if plugins_root.is_dir():
        skill_files = sorted(plugins_root.rglob("SKILL.md"))
    if skill_files != [SKILL_FILE]:
        relative = [str(path.relative_to(REPO_ROOT)) for path in skill_files]
        errors.append("expected one canonical SKILL.md, found: {}".format(relative))

    if not OPENAI_YAML.is_file():
        errors.append("missing agents/openai.yaml in the canonical skill")
    else:
        openai_text = OPENAI_YAML.read_text(encoding="utf-8")
        required_snippets = (
            "display_name: \"Knowledge Compass\"",
            "short_description:",
            "default_prompt:",
            "$knowledge-compass",
            "allow_implicit_invocation: true",
        )
        for snippet in required_snippets:
            if snippet not in openai_text:
                errors.append("agents/openai.yaml is missing {!r}".format(snippet))

    readme_path = REPO_ROOT / "README.md"
    if not readme_path.is_file():
        errors.append("missing README.md")
    else:
        readme = readme_path.read_text(encoding="utf-8")
        required_commands = (
            "/plugin marketplace add hidetodong/knowledge-compass-skill",
            "/plugin install knowledge-compass@knowledge-compass-skill",
            "/knowledge-compass:knowledge-compass",
            "codex plugin marketplace add hidetodong/knowledge-compass-skill",
            "codex plugin add knowledge-compass@knowledge-compass-skill",
            "$knowledge-compass",
            "~/knowledge-compass/",
        )
        for command in required_commands:
            if command not in readme:
                errors.append("README.md is missing {!r}".format(command))

    license_path = REPO_ROOT / "LICENSE"
    if not license_path.is_file() or "MIT License" not in license_path.read_text(encoding="utf-8"):
        errors.append("missing MIT LICENSE")

    json_paths = sorted(path for path in iter_public_files() if path.suffix == ".json")
    for path in json_paths:
        load_json(path, errors)

    banned_names = {".DS_Store", "Thumbs.db", "__pycache__"}
    absolute_path_pattern = re.compile(r"(?:^|[\s\"'])/(?:Users|home)/[^\s\"']+")
    for path in iter_public_files():
        relative = path.relative_to(REPO_ROOT)
        if any(part in banned_names or part.endswith((".pyc", ".pyo")) for part in relative.parts):
            # Ignored local caches do not enter a distribution. Tracked files are
            # checked separately below so an accidentally committed cache fails.
            continue
        if path.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".py", ".html"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append("unable to read public text file: {}".format(relative))
            continue
        if absolute_path_pattern.search(text):
            errors.append("public file contains a personal absolute path: {}".format(relative))

    for tracked in tracked_files(errors):
        first = tracked.split("/", 1)[0]
        if first in LOCAL_ONLY_TRACKED_PATHS:
            errors.append("local Butler/Codex project state must not be tracked: {}".format(tracked))
        parts = tracked.split("/")
        if any(part in banned_names or part.endswith((".pyc", ".pyo")) for part in parts):
            errors.append("tracked cache/junk file: {}".format(tracked))

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Distribution validation failed:")
        for error in errors:
            print("- {}".format(error))
        return 1
    print("Distribution validation passed (Knowledge Compass {}).".format(VERSION))
    return 0


if __name__ == "__main__":
    sys.exit(main())
