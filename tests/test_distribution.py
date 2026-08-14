"""Tests for the dual-host public distribution."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "knowledge-compass"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "knowledge-compass"
VIEWER = SKILL_ROOT / "assets" / "viewer_template.html"


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

        self.assertEqual(claude_marketplace["metadata"]["version"], "0.5.1")
        self.assertEqual(claude_marketplace["plugins"][0]["version"], "0.5.1")
        self.assertEqual(claude_plugin["version"], "0.5.1")
        self.assertEqual(codex_plugin["version"], "0.5.1")

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

    def test_zero_install_delivery_contract_is_explicit(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for value in (
            "先把 JSON 写入磁盘",
            "command -v python3",
            "WindowsApps\\python3.exe",
            "不要运行包管理器、自动安装 Python",
            "knowledge-compass-viewer.html",
            "结构化 Markdown",
            "这一路径**不会**写入中央库",
            "研究和学习路线已经完成",
        ):
            with self.subTest(value=value):
                self.assertIn(value, skill)
        for value in (
            "Python is optional",
            "zero-install offline browser viewer",
            "JSON + structured Markdown",
            "does not upload the guide",
        ):
            with self.subTest(value=value):
                self.assertIn(value, readme)

    def test_offline_viewer_is_packaged_self_contained_and_accessible(self):
        viewer = VIEWER.read_text(encoding="utf-8")
        self.assertEqual(viewer.count("/*__PATH_DATA__*/"), 1)
        self.assertIn(
            '<script id="kc-guide-data" type="application/json">/*__PATH_DATA__*/</script>',
            viewer,
        )
        self.assertIsNone(re.search(r"<script[^>]+\bsrc\s*=", viewer, re.IGNORECASE))
        self.assertIsNone(re.search(r"<link[^>]+\bhref\s*=", viewer, re.IGNORECASE))
        self.assertIsNone(re.search(r"\.innerHTML\s*=", viewer))
        for value in (
            "validateGuideInBrowser",
            "exportStandaloneHtml",
            "new TextDecoder(\"utf-8\",{fatal:true})",
            "URL.createObjectURL",
            "prefers-reduced-motion:reduce",
            "aria-live",
            'input.tabIndex = -1; input.setAttribute("aria-hidden","true")',
            "三步完成 · 不用装任何东西",
            "数据只在本机处理，不会上传",
            "导出独立 HTML",
        ):
            with self.subTest(value=value):
                self.assertIn(value, viewer)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for browser validator tests")
    def test_browser_validator_security_contract(self):
        viewer = VIEWER.read_text(encoding="utf-8")
        executable = viewer.split("<script>\n", 1)[1].rsplit("</script>", 1)[0]
        self.assertEqual(executable.count("bootViewer();"), 1)
        probes = r'''
const valid = {
  topic: "测试指南",
  layers: [{resources: [
    {id:"intro", name:"入门", url:"https://example.com", verified:true},
    {id:"next", name:"进阶", requires:["intro"], verified:false}
  ]}],
  fragments: [], disciplines: [], references: [], plan: []
};
function clone(value){ return JSON.parse(JSON.stringify(value)); }
const unsafe = clone(valid); unsafe.layers[0].resources[0].url = "javascript:alert(1)";
const strictBoolean = clone(valid); strictBoolean.layers[0].resources[0].verified = "true";
const reserved = clone(valid); reserved.layers[0].resources[0].id = "__proto__";
const cycle = clone(valid); cycle.layers[0].resources[0].requires = ["next"];
const explicitNulls = {};
for(const key of ["references","plan","fragments","disciplines"]){
  const probe = clone(valid); probe[key] = null;
  explicitNulls[key] = validateGuideInBrowser(probe);
}
const nullRequires = clone(valid); nullRequires.layers[0].resources[0].requires = null;
explicitNulls.requires = validateGuideInBrowser(nullRequires);
const storageA = clone(valid); storageA._storage_key = "attacker-a";
const storageB = clone(valid); storageB._storage_key = "attacker-b";
const escaped = jsonForHtml({text:"</ScRiPt>&\u2028\u2029"});
process.stdout.write(JSON.stringify({
  valid: validateGuideInBrowser(valid),
  unsafe: validateGuideInBrowser(unsafe),
  strictBoolean: validateGuideInBrowser(strictBoolean),
  reserved: validateGuideInBrowser(reserved),
  cycle: validateGuideInBrowser(cycle),
  explicitNulls,
  suppliedStorageKeyIgnored: browserStorageKey(storageA) === browserStorageKey(storageB),
  escaped
}));
'''
        script = executable.replace("bootViewer();", probes)
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "viewer-contract.js"
            runner.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(runner)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["valid"], [])
        for key in ("unsafe", "strictBoolean", "reserved", "cycle"):
            with self.subTest(key=key):
                self.assertTrue(payload[key])
        for key, errors in payload["explicitNulls"].items():
            with self.subTest(explicit_null=key):
                self.assertTrue(errors)
        self.assertTrue(payload["suppliedStorageKeyIgnored"])
        self.assertNotIn("</ScRiPt>", payload["escaped"])
        for escaped in (r"\u003c", r"\u003e", r"\u0026", r"\u2028", r"\u2029"):
            with self.subTest(escaped=escaped):
                self.assertIn(escaped, payload["escaped"])


if __name__ == "__main__":
    unittest.main()
