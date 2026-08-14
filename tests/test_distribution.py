"""Tests for the dual-host public distribution."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "knowledge-compass"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "knowledge-compass"


def load_json(relative_path):
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


class DistributionTests(unittest.TestCase):
    def test_distribution_validator_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/validate_distribution.py"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_marketplaces_resolve_the_same_plugin(self):
        claude = load_json(".claude-plugin/marketplace.json")
        codex = load_json(".agents/plugins/marketplace.json")

        self.assertEqual(claude["name"], "knowledge-compass-skill")
        self.assertEqual(codex["name"], "knowledge-compass-skill")
        self.assertEqual(claude["plugins"][0]["name"], "knowledge-compass")
        self.assertEqual(codex["plugins"][0]["name"], "knowledge-compass")
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/knowledge-compass")
        self.assertEqual(
            codex["plugins"][0]["source"],
            {"source": "local", "path": "./plugins/knowledge-compass"},
        )

    def test_plugin_versions_are_aligned(self):
        claude_marketplace = load_json(".claude-plugin/marketplace.json")
        claude_plugin = load_json("plugins/knowledge-compass/.claude-plugin/plugin.json")
        codex_plugin = load_json("plugins/knowledge-compass/.codex-plugin/plugin.json")

        self.assertEqual(claude_marketplace["metadata"]["version"], "0.5.0")
        self.assertEqual(claude_marketplace["plugins"][0]["version"], "0.5.0")
        self.assertEqual(claude_plugin["version"], "0.5.0")
        self.assertEqual(codex_plugin["version"], "0.5.0")

    def test_there_is_one_canonical_skill(self):
        skill_files = sorted((REPO_ROOT / "plugins").rglob("SKILL.md"))
        self.assertEqual(skill_files, [SKILL_ROOT / "SKILL.md"])
        self.assertEqual(load_json("plugins/knowledge-compass/.codex-plugin/plugin.json")["skills"], "./skills/")

    def test_codex_interface_invokes_the_canonical_skill(self):
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Knowledge Compass"', metadata)
        self.assertIn("$knowledge-compass", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_readme_has_current_install_and_invocation_commands(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        expected = (
            "/plugin marketplace add hidetodong/knowledge-compass-skill",
            "/plugin install knowledge-compass@knowledge-compass-skill",
            "/knowledge-compass:knowledge-compass",
            "codex plugin marketplace add hidetodong/knowledge-compass-skill",
            "codex plugin add knowledge-compass@knowledge-compass-skill",
            "$knowledge-compass",
            "~/knowledge-compass/",
        )
        for value in expected:
            with self.subTest(value=value):
                self.assertIn(value, readme)


if __name__ == "__main__":
    unittest.main()
