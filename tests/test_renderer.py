import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "knowledge-compass" / "skills" / "knowledge-compass"
RENDERER = SKILL / "scripts" / "view_field_guide.py"
VIEWER = SKILL / "assets" / "viewer_template.html"

URL_PARITY_CASES = (
    ("https://example.com/path?q=1#section", True),
    (" HTTP://EXAMPLE.COM:8080/resource ", True),
    ("https://例子.测试/路径", True),
    ("https://exa_mple.example/resource", True),
    ("https://user:pass@example.com/resource", True),
    ("https://[::1]/resource", True),
    ("https://127.0.0.1:0/resource", True),
    ("https://example.com:65535/resource", True),
    ("https://example.com./resource", True),
    ("https://-example.com/resource", True),
    ("https://example-.com/resource", True),
    ("https://example.com/%zz", True),
    ("https://example.com/\u200bresource", True),
    ("javascript:alert(1)", False),
    ("data:text/html,pwned", False),
    ("//example.com/path", False),
    ("https://", False),
    ("https://exa mple.com/resource", False),
    ("https://example.com\\@evil.test/resource", False),
    ("https://example.com:99999/resource", False),
    ("https://example.com:/resource", False),
    ("https://[::1/resource", False),
    ("https://[v1.foo]/resource", False),
    ("https://[fe80::1%25en0]/resource", False),
    ("https://256.256.256.256/resource", False),
    ("https://999999999/resource", False),
    ("https://127.00.0.1/resource", False),
    ("https://%65xample.com/resource", False),
    ("https://%zz/resource", False),
    ("https://.example.com/resource", False),
    ("https://example..com/resource", False),
    ("https://💩.example/resource", False),
    ("https://example.com|evil/resource", False),
    ("https://example.com/\u0000resource", False),
    ("https://example.com/\ufeffresource", False),
    ("\ufeffhttps://example.com/resource", False),
)

URL_PARITY_HOSTS = (
    "example.com", "EXAMPLE.COM", "example.com.", "exa_mple.com", "-example.com",
    "example-.com", ".example.com", "example..com", "%65xample.com", "%zz",
    "example.com|evil", "example com", "例子.测试", "例え.テスト", "a\u0301.example",
    "💩.example", "０.com", "xn--fsqu00a.xn--0zwm56d", "127.0.0.1",
    "127.00.0.1", "127.1", "0.0.0.0", "255.255.255.255", "256.0.0.1",
    "999999999", "localhost", "a", "a" * 63 + ".com", "a" * 64 + ".com",
    "a." * 126 + "a", "[::1]", "[2001:db8::1]", "[::ffff:192.0.2.128]",
    "[v1.foo]", "[fe80::1%25en0]", "[::1",
)


def valid_guide():
    return {
        "topic": "概率论入门",
        "domain": "数学 · 概率论",
        "fragments": ["大数定律", "中心极限定理"],
        "disciplines": ["数学"],
        "overview": "从随机现象建立可检验的模型。[1]",
        "layers": [
            {
                "emoji": "🌱",
                "title": "入门",
                "resources": [
                    {
                        "id": "intro",
                        "name": "《概率导论》（Introduction to Probability）",
                        "url": "https://example.com/book",
                        "verified": True,
                    },
                    {
                        "id": "course",
                        "requires": ["intro"],
                        "name": "公开课",
                        "url": "https://example.com/course",
                        "verify_note": "尚未完成逐页核验",
                    },
                ],
            }
        ],
        "plan": [{"step": "阶段 1", "detail": "完成入门教材"}],
        "references": [
            {
                "title": "课程主页",
                "source": "示例大学",
                "url": "https://example.com/reference",
            }
        ],
    }


def run_renderer(input_path, library, *extra):
    env = os.environ.copy()
    env["KNOWLEDGE_COMPASS_LIBRARY"] = str(library)
    return subprocess.run(
        [sys.executable, str(RENDERER), str(input_path), "--no-open", *extra],
        cwd=str(input_path.parent),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class RendererTests(unittest.TestCase):
    def write_guide(self, directory, payload=None, name="guide.json"):
        path = Path(directory) / name
        data = valid_guide() if payload is None else payload
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_archive_builds_html_json_and_index_with_explicit_verification_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "library"
            result = run_renderer(self.write_guide(source), library)

            self.assertEqual(result.returncode, 0, result.stderr)
            stem = f"{date.today().isoformat()}-概率论入门"
            self.assertTrue((library / f"{stem}.html").is_file())
            self.assertTrue((library / f"{stem}.json").is_file())
            index = (library / "index.html").read_text(encoding="utf-8")
            self.assertIn('"unverified": 1', index)

    def test_no_archive_writes_beside_input_and_never_creates_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "must-not-exist"
            input_path = self.write_guide(source)

            result = run_renderer(input_path, library, "--no-archive")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((source / "guide.html").is_file())
            self.assertFalse(library.exists())

    def test_no_archive_rejects_implicit_output_for_input_inside_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "library"
            library.mkdir()
            input_path = self.write_guide(library)

            result = run_renderer(input_path, library, "--no-archive")

            self.assertEqual(result.returncode, 2)
            self.assertIn("output must be outside the central library", result.stderr)
            self.assertFalse((library / "guide.html").exists())

    def test_no_archive_allows_library_input_with_explicit_external_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            library.mkdir()
            external = root / "external" / "guide.html"
            input_path = self.write_guide(library)

            result = run_renderer(
                input_path, library, "--no-archive", "--out", str(external)
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(external.is_file())
            self.assertTrue(external.with_suffix(".json").is_file())
            self.assertFalse((library / "guide.html").exists())

    def test_rejects_non_object_payload_with_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = self.write_guide(root, ["not", "an", "object"])
            result = run_renderer(input_path, root / "library", "--no-archive")

            self.assertEqual(result.returncode, 2)
            self.assertIn("top level must be a JSON object", result.stderr)

    def test_rejects_unsafe_resource_and_reference_urls(self):
        payload = valid_guide()
        payload["layers"][0]["resources"][0]["url"] = "javascript:alert(1)"
        payload["references"][0]["url"] = "data:text/html,pwned"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("absolute http(s) URL", result.stderr)
            self.assertFalse((root / "guide.html").exists())

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for validator parity")
    def test_python_and_browser_url_validators_share_acceptance_vectors(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        viewer = VIEWER.read_text(encoding="utf-8")
        executable = viewer.split("<script>\n", 1)[1].rsplit("</script>", 1)[0]
        fixed_vectors = [url for url, _ in URL_PARITY_CASES]
        generated_vectors = [
            scheme + userinfo + host + port + path
            for scheme in ("https://", "HTTP://")
            for userinfo in ("", "user@", "user:pass@", "user@@")
            for host in URL_PARITY_HOSTS
            for port in ("", ":0", ":80", ":00080", ":65535", ":65536", ":", ":abc")
            for path in ("", "/", "/path?q=1#x", "/%zz", "/\u200bpath", "/<x>")
        ]
        vectors = list(dict.fromkeys(fixed_vectors + generated_vectors))
        probes = """
const vectors = %s;
process.stdout.write(JSON.stringify(vectors.map(value => isSafeWebUrl(value))));
""" % json.dumps(vectors, ensure_ascii=False)
        script = executable.replace("bootViewer();", probes)

        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "url-parity.js"
            runner.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(runner)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        browser_results = json.loads(result.stdout)
        python_results = [module.is_safe_web_url(value) for value in vectors]
        expected = [accepted for _, accepted in URL_PARITY_CASES]
        self.assertEqual(python_results[: len(expected)], expected)
        self.assertEqual(browser_results[: len(expected)], expected)
        self.assertEqual(python_results, browser_results)

    def test_malformed_http_url_is_rejected_before_any_output_is_written(self):
        payload = valid_guide()
        payload["layers"][0]["resources"][0]["url"] = "https://exa mple.com/resource"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("absolute http(s) URL", result.stderr)
            self.assertFalse((root / "guide.html").exists())

    def test_embedded_json_escapes_mixed_case_script_breakout(self):
        payload = valid_guide()
        payload["topic"] = "</ScRiPt><script>globalThis.pwned=1</script>"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            html = (root / "guide.html").read_text(encoding="utf-8")
            self.assertNotIn("</ScRiPt>", html)
            self.assertNotIn("<script>globalThis.pwned", html)
            self.assertIn(r"\u003c/ScRiPt\u003e", html)

    def test_python_output_uses_the_same_inert_json_data_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            html = (root / "guide.html").read_text(encoding="utf-8")
            self.assertNotIn("/*__PATH_DATA__*/", html)
            self.assertNotIn("const DATA =", html)
            match = re.search(
                r'<script id="kc-guide-data" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            embedded = json.loads(match.group(1))
            self.assertEqual(embedded["topic"], "概率论入门")
            self.assertRegex(embedded["_storage_key"], r"^[0-9a-f]{24}$")

    def test_inline_fails_closed_unless_placeholder_is_unique(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        placeholder = "__PAYLOAD__"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, template, count in (
                ("missing.html", "<p>no slot</p>", 0),
                ("duplicate.html", "__PAYLOAD__ + __PAYLOAD__", 2),
            ):
                with self.subTest(count=count):
                    path = root / name
                    path.write_text(template, encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValueError, "must appear exactly once.*found {}".format(count)
                    ):
                        module.inline(path, placeholder, {"safe": True})

    def test_external_archives_with_same_topic_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "library"
            first = run_renderer(self.write_guide(source, name="first.json"), library)
            second = run_renderer(self.write_guide(source, name="second.json"), library)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            stem = f"{date.today().isoformat()}-概率论入门"
            self.assertTrue((library / f"{stem}.json").is_file())
            self.assertTrue((library / f"{stem}-2.json").is_file())

    def test_library_index_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "library"
            library.mkdir()
            sentinel = root / "sentinel.txt"
            sentinel.write_text("do not overwrite", encoding="utf-8")
            (library / "index.html").symlink_to(sentinel)

            result = run_renderer(self.write_guide(source), library)

            self.assertEqual(result.returncode, 2)
            self.assertIn("refusing to write through symlink", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not overwrite")

    def test_colliding_symlink_pair_is_skipped_without_touching_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "library"
            library.mkdir()
            sentinel_html = root / "sentinel.html"
            sentinel_json = root / "sentinel.json"
            sentinel_html.write_text("html sentinel", encoding="utf-8")
            sentinel_json.write_text("json sentinel", encoding="utf-8")
            stem = f"{date.today().isoformat()}-概率论入门"
            (library / f"{stem}.html").symlink_to(sentinel_html)
            (library / f"{stem}.json").symlink_to(sentinel_json)

            result = run_renderer(self.write_guide(source), library)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sentinel_html.read_text(encoding="utf-8"), "html sentinel")
            self.assertEqual(sentinel_json.read_text(encoding="utf-8"), "json sentinel")
            self.assertTrue((library / f"{stem}-2.html").is_file())
            self.assertTrue((library / f"{stem}-2.json").is_file())

    def test_out_requires_html_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root), root / "library", "--out", str(root / "broken.json")
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--out must end in .html", result.stderr)

    def test_out_cannot_replace_library_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            library.mkdir()
            result = run_renderer(
                self.write_guide(root), library, "--out", str(library / "index.html")
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot replace the library index.html", result.stderr)
            self.assertFalse((library / "index.json").exists())

    def test_topic_control_character_is_rejected_before_path_creation(self):
        payload = valid_guide()
        payload["topic"] = "nul\u0000topic"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("topic must not contain control characters", result.stderr)

    def test_long_multibyte_topic_produces_filesystem_safe_name(self):
        payload = valid_guide()
        payload["topic"] = "知识" * 200
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            result = run_renderer(self.write_guide(root, payload), library)

            self.assertEqual(result.returncode, 0, result.stderr)
            guide_files = [path for path in library.glob("*.html") if path.name != "index.html"]
            self.assertEqual(len(guide_files), 1)
            self.assertLessEqual(len(guide_files[0].name.encode("utf-8")), 255)

    def test_rejects_unknown_dependency_id(self):
        payload = valid_guide()
        payload["layers"][0]["resources"][1]["requires"] = ["missing"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("references unknown id: missing", result.stderr)

    def test_rejects_reserved_and_unstable_resource_ids(self):
        for resource_id in ("constructor", "__proto__", "Has Spaces"):
            with self.subTest(resource_id=resource_id), tempfile.TemporaryDirectory() as tmp:
                payload = valid_guide()
                payload["layers"][0]["resources"][0]["id"] = resource_id
                root = Path(tmp)
                result = run_renderer(
                    self.write_guide(root, payload), root / "library", "--no-archive"
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("must not be a reserved object key", result.stderr)

    def test_collision_safe_guides_use_distinct_progress_storage_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            library = root / "library"
            first = run_renderer(self.write_guide(source, name="first.json"), library)
            second = run_renderer(self.write_guide(source, name="second.json"), library)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            html_files = sorted(path for path in library.glob("*.html") if path.name != "index.html")
            self.assertEqual(len(html_files), 2)
            keys = set()
            for path in html_files:
                match = re.search(r'"_storage_key": "([0-9a-f]{24})"', path.read_text(encoding="utf-8"))
                self.assertIsNotNone(match)
                keys.add(match.group(1))
            self.assertEqual(len(keys), 2)

    def test_rejects_cyclic_resource_dependencies(self):
        payload = valid_guide()
        payload["layers"][0]["resources"][0]["requires"] = ["course"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_renderer(
                self.write_guide(root, payload), root / "library", "--no-archive"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("requires contains a cycle", result.stderr)

    def test_index_percent_encodes_filename_that_looks_like_a_url_scheme(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            guide = valid_guide()
            (library / "javascript:alert(1).json").write_text(
                json.dumps(guide), encoding="utf-8"
            )
            (library / "javascript:alert(1).html").write_text("ok", encoding="utf-8")

            index_path, count = module.build_index(library)
            index = index_path.read_text(encoding="utf-8")

            self.assertEqual(count, 1)
            self.assertNotIn('"html": "javascript:', index)
            self.assertIn("javascript%3Aalert%281%29.html", index)


if __name__ == "__main__":
    unittest.main()
