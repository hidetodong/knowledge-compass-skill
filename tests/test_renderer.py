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


def guide_with_outcomes():
    payload = valid_guide()
    payload["outcomes_summary"] = "学完大致相当于读完一门入门课，离独立研究还差习题训练。[1]"
    payload["outcomes"] = [
        {"kind": "能力", "title": "能用模拟验证大数定律", "check": "十分钟内写出抛硬币模拟"},
        {"kind": "知识", "title": "明白样本均值为什么会稳定", "detail": "靠阶段 1 获得[1]"},
        {"kind": "能力", "title": "能读懂教材里的极限定理证明"},
    ]
    return payload


# Each case breaks one outcome rule; the browser must report the exact same errors.
INVALID_OUTCOME_CASES = (
    ("outcomes", {}, ["outcomes must be an array"]),
    ("outcomes", None, ["outcomes must be an array"]),
    ("outcomes", ["知识"], ["outcomes[0] must be an object"]),
    ("outcomes", [{"kind": "技能", "title": "t"}], ["outcomes[0].kind must be 知识 or 能力"]),
    ("outcomes", [{"title": "t"}], ["outcomes[0].kind must be 知识 or 能力"]),
    ("outcomes", [{"kind": "知识"}], ["outcomes[0].title must be a non-empty string"]),
    ("outcomes", [{"kind": "知识", "title": " \u3000\n"}], ["outcomes[0].title must be a non-empty string"]),
    ("outcomes", [{"kind": "知识", "title": 7}], ["outcomes[0].title must be a non-empty string"]),
    ("outcomes", [{"kind": "知识", "title": "t", "detail": 1}], ["outcomes[0].detail must be a string"]),
    ("outcomes", [{"kind": "能力", "title": "t", "check": []}], ["outcomes[0].check must be a string"]),
    # JSON.parse keeps "__proto__" as an ordinary key, so its contents must not count as the item's fields.
    (
        "outcomes",
        [{"__proto__": {"kind": "知识", "title": "t"}}],
        ["outcomes[0].kind must be 知识 or 能力", "outcomes[0].title must be a non-empty string"],
    ),
    ("outcomes_summary", 1, ["outcomes_summary must be a string"]),
    ("outcomes_summary", None, ["outcomes_summary must be a string"]),
)


def run_viewer_probe(probes):
    """Run the viewer script in Node with bootViewer() replaced by probe code; return its stdout JSON."""
    viewer = VIEWER.read_text(encoding="utf-8")
    executable = viewer.split("<script>\n", 1)[1].rsplit("</script>", 1)[0]
    script = executable.replace("bootViewer();", probes)
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "viewer-probe.js"
        runner.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [shutil.which("node"), str(runner)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class LearningOutcomeTests(unittest.TestCase):
    def render(self, payload):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / "guide.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return root, run_renderer(path, root / "library", "--no-archive")

    def test_outcomes_are_accepted_and_embedded_unchanged(self):
        payload = guide_with_outcomes()
        root, result = self.render(payload)

        self.assertEqual(result.returncode, 0, result.stderr)
        html = (root / "guide.html").read_text(encoding="utf-8")
        match = re.search(
            r'<script id="kc-guide-data" type="application/json">(.*?)</script>', html, re.DOTALL
        )
        embedded = json.loads(match.group(1))
        self.assertEqual(embedded["outcomes"], payload["outcomes"])
        self.assertEqual(embedded["outcomes_summary"], payload["outcomes_summary"])

    def test_invalid_outcomes_are_rejected_before_any_output_is_written(self):
        for key, value, expected in INVALID_OUTCOME_CASES:
            with self.subTest(key=key, value=value):
                payload = guide_with_outcomes()
                payload[key] = value
                root, result = self.render(payload)

                self.assertEqual(result.returncode, 2)
                for message in expected:
                    self.assertIn(message, result.stderr)
                self.assertFalse((root / "guide.html").exists())
                self.assertFalse((root / "library").exists())

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for validator parity")
    def test_python_and_browser_report_identical_outcome_errors(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        payloads = [valid_guide(), guide_with_outcomes()]
        for key, value, _ in INVALID_OUTCOME_CASES:
            payload = guide_with_outcomes()
            payload[key] = value
            payloads.append(payload)
        multi = guide_with_outcomes()
        multi["outcomes"] = [{"kind": 1, "title": "", "detail": 2, "check": 3}, None]
        payloads.append(multi)
        # Every character either runtime calls whitespace, plus look-alikes that are not blank.
        for char in module.BLANK_CHARS + "\u200b\u180ea":
            payload = guide_with_outcomes()
            payload["outcomes"][0]["title"] = char * 2
            payloads.append(payload)
        # Keys that would touch the prototype chain if parsed carelessly stay ordinary, ignored keys.
        inherited = guide_with_outcomes()
        inherited["outcomes"][0]["__proto__"] = {"detail": 1}
        inherited["outcomes"][1]["constructor"] = 1
        inherited["__proto__"] = {"outcomes": 5}
        payloads.append(inherited)

        # Feed the browser through JSON.parse, exactly like an imported or embedded guide.
        browser = run_viewer_probe(
            "const payloads = JSON.parse(%s);\nprocess.stdout.write(JSON.stringify(payloads.map(validateGuideInBrowser)));"
            % json.dumps(json.dumps(payloads))
        )
        python = [module.validate_guide(payload) for payload in payloads]

        blank_start = 3 + len(INVALID_OUTCOME_CASES)
        blank_results = python[blank_start : blank_start + len(module.BLANK_CHARS)]
        self.assertEqual(python[:2], [[], []])
        self.assertTrue(all(errors for errors in python[2:blank_start]))
        self.assertEqual(
            blank_results,
            [["outcomes[0].title must be a non-empty string"]] * len(module.BLANK_CHARS),
        )
        self.assertEqual(python[-4:], [[], [], [], []])
        self.assertEqual(python, browser)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for render tests")
    def test_outcome_section_groups_items_and_omits_empty_parts(self):
        probes = r"""
class FakeText { constructor(text){ this.data = String(text); } get textContent(){ return this.data; } }
class FakeElement {
  constructor(tag){ this.tagName = tag; this.className = ""; this.id = ""; this.attrs = {}; this.childNodes = []; this.own = ""; }
  appendChild(child){ this.childNodes.push(child); return child; }
  setAttribute(name, value){ this.attrs[name] = String(value); }
  set textContent(value){ this.childNodes = []; this.own = String(value); }
  get textContent(){ return this.own + this.childNodes.map(child => child.textContent).join(""); }
}
globalThis.document = {
  createElement: tag => new FakeElement(tag),
  createTextNode: text => new FakeText(text)
};
function dump(node){
  if(node === null) return null;
  if(node instanceof FakeText) return node.data;
  return {tag:node.tagName, cls:node.className, id:node.id, attrs:node.attrs, href:node.href || null,
          own:node.own, text:node.textContent, children:node.childNodes.map(dump)};
}
REFS = [{title:"课程主页"}];
const mixed = [
  {kind:"能力", title:"A 能做", check:"自检 A"},
  {kind:"知识", title:"B 懂得[1]", detail:"阶段 1"},
  {kind:"能力", title:"C 能做"}
];
process.stdout.write(JSON.stringify({
  full: dump(renderOutcomes("大致水平[1]", mixed)),
  knowledgeOnly: dump(renderOutcomes(undefined, [mixed[1]])),
  abilityOnly: dump(renderOutcomes(undefined, [mixed[0], mixed[2]])),
  summaryOnly: dump(renderOutcomes("只有水平说明", [])),
  absent: dump(renderOutcomes(undefined, undefined)),
  emptyList: dump(renderOutcomes(undefined, [])),
  blankSummary: dump(renderOutcomes(" \u3000", [])),
  blankParts: dump(renderOutcomes(undefined, [{kind:"知识", title:"T", detail:" \u3000", check:"\n"}]))
}));
"""
        result = run_viewer_probe(probes)

        full = result["full"]
        self.assertEqual((full["tag"], full["cls"]), ("section", "outcomes"))
        self.assertEqual(full["attrs"]["aria-labelledby"], "outcomes-title")
        heading, summary, groups = full["children"]
        self.assertEqual((heading["tag"], heading["id"], heading["text"]), ("h2", "outcomes-title", "🎯 学成之后"))
        self.assertEqual((summary["cls"], summary["text"]), ("outcomes-summary", "大致水平[1]"))
        self.assertEqual(summary["children"][1]["cls"], "cite")
        self.assertEqual(summary["children"][1]["children"][0]["href"], "#ref-1")
        self.assertEqual(
            [group["cls"] for group in groups["children"]],
            ["outcome-group knowledge", "outcome-group ability"],
        )
        knowledge, ability = groups["children"]
        self.assertEqual(knowledge["children"][0]["text"], "🧠 你会懂得")
        self.assertEqual(ability["children"][0]["text"], "🛠 你能做到")
        self.assertEqual(
            [item["children"][0]["text"] for item in ability["children"][1]["children"]],
            ["A 能做", "C 能做"],
        )
        first_ability = ability["children"][1]["children"][0]
        check = first_ability["children"][1]
        self.assertEqual(check["cls"], "outcome-check")
        self.assertEqual((check["children"][0]["cls"], check["children"][0]["text"]), ("check-label", "自检"))
        self.assertEqual(check["children"][1]["cls"], "sr-only")
        self.assertEqual(check["text"], "自检：自检 A")
        knowledge_item = knowledge["children"][1]["children"][0]
        self.assertEqual(
            [child["cls"] for child in knowledge_item["children"]], ["outcome-title", "outcome-detail"]
        )

        self.assertEqual(
            [group["cls"] for group in result["knowledgeOnly"]["children"][1]["children"]],
            ["outcome-group knowledge"],
        )
        self.assertEqual(
            [group["cls"] for group in result["abilityOnly"]["children"][1]["children"]],
            ["outcome-group ability"],
        )
        self.assertEqual(
            [child["cls"] for child in result["summaryOnly"]["children"]], ["", "outcomes-summary"]
        )
        blank_item = result["blankParts"]["children"][1]["children"][0]["children"][1]["children"][0]
        self.assertEqual([child["cls"] for child in blank_item["children"]], ["outcome-title"])
        for key in ("absent", "emptyList", "blankSummary"):
            with self.subTest(key=key):
                self.assertIsNone(result[key])

    def test_outcome_section_sits_between_route_and_references(self):
        viewer = VIEWER.read_text(encoding="utf-8")
        body = viewer.split("function render(data){", 1)[1].split("\nfunction ", 1)[0]
        route = body.index("rt.appendChild(richP(null, data.route));")
        outcomes = body.index("renderOutcomes(data.outcomes_summary, data.outcomes)")
        references = body.index("renderReferences(REFS)")
        self.assertLess(route, outcomes)
        self.assertLess(outcomes, references)


def guide_with_classification():
    payload = valid_guide()
    payload["classification"] = {
        "isced": [{"code": "0541", "name": "数学"}, {"code": "0542", "name": "统计学"}],
        "subjects": [{"qid": "Q5862903", "name": "概率论"}],
    }
    return payload


FULLWIDTH_0412 = "".join(chr(0xFF10 + int(digit)) for digit in "0412")
ARABIC_INDIC_0412 = "".join(chr(0x0660 + int(digit)) for digit in "0412")
IDEOGRAPHIC_SPACE = chr(0x3000)
CODE_ERROR = "classification.isced[0].code must be a 4-digit string"
QID_ERROR = "classification.subjects[0].qid must be a Wikidata id like Q123"

# Each case breaks one shape rule of `classification`; Python and the browser must report exactly
# these errors. Non-ASCII digits and trailing newlines would slip past Python's \d and $.
INVALID_CLASSIFICATION_CASES = (
    (None, ["classification must be an object"]),
    ([], ["classification must be an object"]),
    ("0412", ["classification must be an object"]),
    ({"isced": {"code": "0412", "name": "金融"}}, ["classification.isced must be an array"]),
    ({"subjects": None}, ["classification.subjects must be an array"]),
    ({"isced": ["0412"]}, ["classification.isced[0] must be an object"]),
    ({"subjects": [None]}, ["classification.subjects[0] must be an object"]),
    ({"isced": [{"code": "412", "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": 412, "name": "金融"}]}, [CODE_ERROR]),
    # A number with the right digit count must still fail on its type, not only on the pattern.
    ({"isced": [{"code": 1234, "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": "04120", "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": "x0412", "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": "0412 ", "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": FULLWIDTH_0412, "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": ARABIC_INDIC_0412, "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"code": "0412\n", "name": "金融"}]}, [CODE_ERROR]),
    ({"isced": [{"name": "金融"}]}, [CODE_ERROR]),
    ({"subjects": [{"qid": "q123", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "Q0123", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "Q", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "Q12a", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "Q123\n", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "Q" + FULLWIDTH_0412[1:], "name": "概率论"}]}, [QID_ERROR]),
    # Prefixed ids and full entity URLs are the likeliest model slips; both ends must anchor the pattern.
    ({"subjects": [{"qid": "wd:Q123", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": "https://www.wikidata.org/wiki/Q123", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": " Q123", "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"qid": 123, "name": "概率论"}]}, [QID_ERROR]),
    ({"subjects": [{"name": "概率论"}]}, [QID_ERROR]),
    (
        {"subjects": [{"qid": "Q123", "name": ""}]},
        ["classification.subjects[0].name must be a non-empty string"],
    ),
    (
        {"isced": [{"code": "0412", "name": " " + IDEOGRAPHIC_SPACE + "\n"}]},
        ["classification.isced[0].name must be a non-empty string"],
    ),
    ({"isced": [{"code": "0412"}]}, ["classification.isced[0].name must be a non-empty string"]),
    (
        {"subjects": [{"qid": "Q123", "name": 7}]},
        ["classification.subjects[0].name must be a non-empty string"],
    ),
    # JSON.parse keeps "__proto__" as an ordinary key, so its contents must not count as the item's fields.
    (
        {"subjects": [{"__proto__": {"qid": "Q123", "name": "概率论"}}]},
        [QID_ERROR, "classification.subjects[0].name must be a non-empty string"],
    ),
    (
        {
            "isced": [{"code": "0412", "name": "金融"}, {"code": 1, "name": ""}],
            "subjects": [{"qid": "x"}],
        },
        [
            "classification.isced[1].code must be a 4-digit string",
            "classification.isced[1].name must be a non-empty string",
            QID_ERROR,
            "classification.subjects[0].name must be a non-empty string",
        ],
    ),
)


class ClassificationTests(unittest.TestCase):
    def render(self, payload):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / "guide.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return root, run_renderer(path, root / "library", "--no-archive")

    @staticmethod
    def embedded(root):
        html = (root / "guide.html").read_text(encoding="utf-8")
        match = re.search(
            r'<script id="kc-guide-data" type="application/json">(.*?)</script>', html, re.DOTALL
        )
        return json.loads(match.group(1))

    def test_classification_is_accepted_and_embedded_unchanged(self):
        payload = guide_with_classification()
        root, result = self.render(payload)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.embedded(root)["classification"], payload["classification"])

    def test_well_formed_but_unknown_identifiers_are_not_looked_up(self):
        payload = guide_with_classification()
        payload["classification"] = {
            "isced": [{"code": "9999", "name": "不存在的细类"}],
            "subjects": [{"qid": "Q999999999999", "name": "不存在的条目"}],
        }
        root, result = self.render(payload)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.embedded(root)["classification"], payload["classification"])

    def test_guides_without_classification_render_as_before(self):
        root, result = self.render(valid_guide())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("classification", self.embedded(root))

    def test_invalid_classification_is_rejected_before_any_output_is_written(self):
        for value, expected in INVALID_CLASSIFICATION_CASES:
            with self.subTest(value=value):
                payload = valid_guide()
                payload["classification"] = value
                root, result = self.render(payload)

                self.assertEqual(result.returncode, 2)
                for message in expected:
                    self.assertIn(message, result.stderr)
                self.assertFalse((root / "guide.html").exists())

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for validator parity")
    def test_python_and_browser_report_identical_classification_errors(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        valid = [valid_guide(), guide_with_classification()]
        for value in (
            {},
            {"isced": [], "subjects": []},
            {"isced": [{"code": "9999", "name": "x"}], "subjects": [{"qid": "Q999999999999", "name": "y"}]},
            # Unknown keys are ignored, like everywhere else in the guide schema.
            {"isced": [{"code": "0412", "name": "金融", "note": 1}], "other": 5},
        ):
            payload = valid_guide()
            payload["classification"] = value
            valid.append(payload)
        # Keys that would touch the prototype chain if parsed carelessly stay ordinary, ignored keys.
        inherited = guide_with_classification()
        inherited["classification"]["__proto__"] = {"isced": 5}
        inherited["classification"]["isced"][0]["constructor"] = 1
        inherited["classification"]["subjects"][0]["__proto__"] = {"qid": 5}
        valid.append(inherited)
        outer = valid_guide()
        outer["__proto__"] = {"classification": 5}
        valid.append(outer)

        invalid = []
        for value, _ in INVALID_CLASSIFICATION_CASES:
            payload = valid_guide()
            payload["classification"] = value
            invalid.append(payload)

        # Every character either runtime calls whitespace is blank; look-alikes are not.
        blank, lookalike = [], []
        for chars, bucket in ((module.BLANK_CHARS, blank), (chr(0x200B) + chr(0x180E) + "a", lookalike)):
            for char in chars:
                payload = guide_with_classification()
                payload["classification"]["subjects"][0]["name"] = char * 2
                bucket.append(payload)

        payloads = valid + invalid + blank + lookalike
        # Feed the browser through JSON.parse, exactly like an imported or embedded guide.
        browser = run_viewer_probe(
            "const payloads = JSON.parse(%s);\nprocess.stdout.write(JSON.stringify(payloads.map(validateGuideInBrowser)));"
            % json.dumps(json.dumps(payloads))
        )
        python = [module.validate_guide(payload) for payload in payloads]

        self.assertEqual(python[: len(valid)], [[]] * len(valid))
        self.assertEqual(
            python[len(valid) : len(valid) + len(invalid)],
            [expected for _, expected in INVALID_CLASSIFICATION_CASES],
        )
        self.assertEqual(
            python[len(valid) + len(invalid) : len(valid) + len(invalid) + len(blank)],
            [["classification.subjects[0].name must be a non-empty string"]] * len(blank),
        )
        self.assertEqual(python[-len(lookalike) :], [[]] * len(lookalike))
        self.assertEqual(python, browser)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for validator parity")
    def test_browser_ignores_classification_fields_inherited_from_the_prototype(self):
        probes = r"""
globalThis.document = {
  createElement: tag => ({tagName: tag, childNodes: [], appendChild(child){ this.childNodes.push(child); return child; }}),
  createTextNode: text => ({data: String(text)})
};
const polluted = ["classification","isced","subjects","code","qid","name"];
const values = {classification: 5, isced: 5, subjects: 5, code: "0412", qid: "Q1", name: "继承来的"};
polluted.forEach(key => Object.defineProperty(Object.prototype, key, {value: values[key], configurable: true, writable: true}));
const result = {
  noClassification: validateGuideInBrowser({topic:"t", layers:[{resources:[]}], references:[], plan:[], fragments:[], disciplines:[]}),
  emptyItems: validateClassificationInBrowser({classification: {isced: [{}], subjects: [{}]}}),
  emptyGroups: validateClassificationInBrowser({classification: {}}),
  rendered: renderClassification({isced: [{}], subjects: [{}]})
};
polluted.forEach(key => delete Object.prototype[key]);
process.stdout.write(JSON.stringify(result));
"""
        result = run_viewer_probe(probes)

        self.assertEqual(result["noClassification"], [])
        self.assertEqual(
            result["emptyItems"],
            [
                CODE_ERROR,
                "classification.isced[0].name must be a non-empty string",
                QID_ERROR,
                "classification.subjects[0].name must be a non-empty string",
            ],
        )
        self.assertEqual(result["emptyGroups"], [])
        self.assertIsNone(result["rendered"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for render tests")
    def test_classification_row_shows_both_layers_and_omits_empty_parts(self):
        probes = r"""
class FakeText { constructor(text){ this.data = String(text); } get textContent(){ return this.data; } }
class FakeElement {
  constructor(tag){ this.tagName = tag; this.className = ""; this.childNodes = []; this.own = ""; }
  appendChild(child){ this.childNodes.push(child); return child; }
  set textContent(value){ this.childNodes = []; this.own = String(value); }
  get textContent(){ return this.own + this.childNodes.map(child => child.textContent).join(""); }
}
globalThis.document = {
  createElement: tag => new FakeElement(tag),
  createTextNode: text => new FakeText(text)
};
function dump(node){
  if(node === null) return null;
  if(node instanceof FakeText) return node.data;
  return {tag:node.tagName, cls:node.className, own:node.own, text:node.textContent,
          href:node.href || null, target:node.target || null, rel:node.rel || null, title:node.title || null,
          children:node.childNodes.map(dump)};
}
const isced = [{code:"0541", name:"数学"}, {code:"0542", name:"<b>统计学</b>"}];
const subjects = [{qid:"Q5862903", name:"概率论"}];
process.stdout.write(JSON.stringify({
  both: dump(renderClassification({isced, subjects})),
  iscedOnly: dump(renderClassification({isced})),
  subjectsOnly: dump(renderClassification({subjects})),
  emptyLists: dump(renderClassification({isced: [], subjects: []})),
  absent: dump(renderClassification(undefined)),
  malformed: dump(renderClassification({isced: [{code:"412", name:"金融"}], subjects: [{qid:"q1", name:"x"}, {qid:"Q1", name:" "}]}))
}));
"""
        result = run_viewer_probe(probes)

        both = result["both"]
        self.assertEqual((both["tag"], both["cls"]), ("div", "disc-row class-row"))
        label, math, statistics, subject = both["children"]
        self.assertEqual((label["cls"], label["text"]), ("lab", "🏷 学科分类"))
        for tag, code, name in ((math, "0541", "数学"), (statistics, "0542", "<b>统计学</b>")):
            with self.subTest(code=code):
                self.assertEqual((tag["tag"], tag["cls"]), ("span", "disc isced"))
                self.assertEqual(tag["children"][0]["cls"], "code")
                self.assertEqual(tag["children"][0]["text"], code)
                self.assertEqual(tag["children"][1], name)
        self.assertEqual((subject["tag"], subject["cls"], subject["text"]), ("a", "disc subject", "概率论"))
        self.assertEqual(subject["href"], "https://www.wikidata.org/wiki/Q5862903")
        self.assertEqual(subject["target"], "_blank")
        self.assertEqual(subject["rel"], "noopener noreferrer")
        self.assertEqual(subject["title"], "维基数据 Q5862903")

        self.assertEqual(
            [child["cls"] for child in result["iscedOnly"]["children"]],
            ["lab", "disc isced", "disc isced"],
        )
        self.assertEqual(
            [child["cls"] for child in result["subjectsOnly"]["children"]], ["lab", "disc subject"]
        )
        for key in ("emptyLists", "absent", "malformed"):
            with self.subTest(key=key):
                self.assertIsNone(result[key])

    def test_classification_row_sits_under_disciplines_inside_the_hero(self):
        viewer = VIEWER.read_text(encoding="utf-8")
        body = viewer.split("function render(data){", 1)[1].split("\nfunction ", 1)[0]
        disciplines = body.index('el("span","lab","📚 学科归属")')
        classification = body.index("const classRow = renderClassification(data.classification);")
        attached = body.index("if(classRow) hero.appendChild(classRow);")
        hero = body.index("app.appendChild(hero);")
        self.assertLess(disciplines, classification)
        self.assertLess(classification, attached)
        self.assertLess(attached, hero)

    def test_library_index_carries_only_validated_classification_fields(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            tagged = guide_with_classification()
            expected = json.loads(json.dumps(tagged["classification"]))
            # Unknown keys pass validation but must not reach the index, least of all "__proto__".
            tagged["classification"]["__proto__"] = {"isced": [{"code": "<b>x</b>", "name": 5}]}
            tagged["classification"]["notes"] = "旁注"
            tagged["classification"]["isced"][0]["url"] = "javascript:alert(1)"
            tagged["classification"]["subjects"][0]["__proto__"] = {"qid": "javascript:alert(1)"}
            untagged = valid_guide()
            untagged["topic"] = "统计学入门"
            for name, guide in (("tagged", tagged), ("untagged", untagged)):
                (library / f"{name}.json").write_text(
                    json.dumps(guide, ensure_ascii=False), encoding="utf-8"
                )
                (library / f"{name}.html").write_text("ok", encoding="utf-8")

            index_path, count = module.build_index(library)
            index = index_path.read_text(encoding="utf-8")

        self.assertEqual(count, 2)
        literal = re.search(r"const DATA = (.*?);\n", index).group(1)
        by_topic = {entry["topic"]: entry for entry in json.loads(literal)}
        self.assertEqual(by_topic["概率论入门"]["classification"], expected)
        self.assertEqual(by_topic["统计学入门"]["classification"], {})

        if shutil.which("node"):
            # Evaluate the payload the way index.html does: as an object literal, not via JSON.parse.
            probe = (
                "const DATA = %s;\n"
                "const tags = DATA.find(entry => entry.topic === \"概率论入门\").classification;\n"
                "process.stdout.write(JSON.stringify({keys: Object.keys(tags),\n"
                "  plainProto: Object.getPrototypeOf(tags) === Object.prototype,\n"
                "  itemProtos: tags.subjects.every(item => Object.getPrototypeOf(item) === Object.prototype),\n"
                "  isced: tags.isced}));" % literal
            )
            with tempfile.TemporaryDirectory() as tmp:
                runner = Path(tmp) / "index-probe.js"
                runner.write_text(probe, encoding="utf-8")
                result = subprocess.run(
                    [shutil.which("node"), str(runner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, check=False,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluated = json.loads(result.stdout)
            self.assertEqual(evaluated["keys"], ["isced", "subjects"])
            self.assertTrue(evaluated["plainProto"])
            self.assertTrue(evaluated["itemProtos"])
            self.assertEqual(evaluated["isced"], expected["isced"])

    def test_library_index_skips_guides_with_malformed_classification(self):
        spec = importlib.util.spec_from_file_location("view_field_guide", RENDERER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            broken = guide_with_classification()
            broken["classification"]["subjects"][0]["qid"] = "wd:Q5862903"
            (library / "broken.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
            (library / "broken.html").write_text("ok", encoding="utf-8")

            index_path, count = module.build_index(library)
            index = index_path.read_text(encoding="utf-8")

        self.assertEqual(count, 0)
        self.assertEqual(json.loads(re.search(r"const DATA = (.*?);\n", index).group(1)), [])


if __name__ == "__main__":
    unittest.main()
