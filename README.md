# Knowledge Compass

Knowledge Compass is an Agent Skill for **Claude Code** and **Codex**. Give it a few unfamiliar terms and it will identify the field they belong to, confirm that interpretation with you, verify authoritative sources, and turn the result into a layered learning roadmap with a self-contained interactive webpage.

中文简介：把一组零散陌生词反推出所属领域，核实权威来源，再生成分层、可执行、可归档的学习路线。

## What it does

1. Maps scattered terms to one to three candidate fields.
2. Pauses for confirmation before starting the expensive research phase.
3. Verifies books, papers, courses, standards, and institutional sources.
4. Builds a staged learning route with prerequisites and source dependencies.
5. Delivers the guide locally: automatically rendered and archived with Python, or through a zero-install offline browser viewer when Python is unavailable.

Knowledge Compass is useful for prompts such as:

> I keep hearing “collective representation”, “social fact”, and “anomie”. What field is this, and where should I start learning it?

> 这几个名词属于什么领域？请用权威资料给我一条从入门到进阶的学习路径。

## Requirements

- Claude Code or Codex with plugin support
- Internet access during source discovery and verification

**Python is optional.** If `python3` 3.8 or newer is already available, Knowledge Compass uses it for automatic rendering, archiving, and library indexing. If it is not available, the skill does not install Python or ask you to use a terminal: it gives you an offline browser viewer instead. If no local browser can be opened either, you still receive the complete JSON and a structured Markdown guide.

The Python renderer has no third-party dependencies. The browser fallback is bundled with the skill, runs locally, and does not upload the guide.

## Install in Claude Code

Run these commands inside Claude Code:

```text
/plugin marketplace add hidetodong/knowledge-compass-skill
/plugin install knowledge-compass@knowledge-compass-skill
```

Invoke it explicitly with:

```text
/knowledge-compass:knowledge-compass
```

You can also describe the problem naturally; the skill may be selected automatically when your request matches its purpose.

## Install in Codex

Run these commands in a terminal:

```bash
codex plugin marketplace add hidetodong/knowledge-compass-skill
codex plugin add knowledge-compass@knowledge-compass-skill
```

Invoke it explicitly in a Codex prompt with:

```text
$knowledge-compass
```

Restart the host after installation if the new skill is not visible in the current session.

## Delivery paths

| Environment | What you receive | Central archive and `index.html` |
|---|---|---|
| `python3` 3.8+ is detected | JSON + self-contained HTML | Updated automatically |
| No compatible Python, local browser available | JSON + structured Markdown + `knowledge-compass-viewer.html`; import the JSON and export a self-contained HTML page | Not updated |
| Neither Python nor a local browser is available | JSON + structured Markdown | Not updated; only the interactive view and library features are unavailable |

If you do not know how to install Python, **you do not need to learn or install it for this skill**. Open `knowledge-compass-viewer.html`, select or drag in the JSON file beside it, and click **导出独立 HTML** (Export standalone HTML) after the page confirms the guide is valid. The three-step page works offline and keeps the data on your device.

The exported browser page is a complete, shareable guide, but the zero-install path deliberately does not write to `~/knowledge-compass/` or rebuild the central `index.html`. Use the automatic Python path later if you want the long-term multi-guide library.

## Automatic local library (optional Python path)

When `python3` 3.8 or newer is available, generated guides are archived by default in:

```text
~/knowledge-compass/
```

Each guide keeps its JSON source beside its rendered HTML. The same directory also contains `index.html`, which links all archived guides. Override the library location for one run with `--library`, or set `KNOWLEDGE_COMPASS_LIBRARY` for a persistent custom location:

```bash
export KNOWLEDGE_COMPASS_LIBRARY="/path/to/your/library"
```

Use `--no-archive` to render beside an input JSON that is outside the library, and `--no-open` when running headlessly. If the input already lives in the library, pair `--no-archive` with `--out` pointing outside it; the renderer rejects a no-archive output inside the library.

`--out path/name.html` explicitly owns that output pair: it replaces `path/name.html` and its sibling `path/name.json` when they already exist. Choose a fresh stem if those files contain unrelated work.

```bash
python3 plugins/knowledge-compass/skills/knowledge-compass/scripts/view_field_guide.py \
  path/to/guide.json --no-archive --no-open
```

## One skill, both hosts

The repository deliberately keeps one canonical implementation:

```text
plugins/knowledge-compass/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
└── skills/knowledge-compass/       # single source of truth
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── assets/
    ├── evals/
    └── scripts/
```

Claude Code and Codex load the same `SKILL.md`, renderer, templates, and eval cases. Host-specific files only describe discovery and presentation; there is no forked skill implementation.

## Security and privacy boundaries

- Guides and progress data stay local. The plugin has no MCP server, cloud service, analytics, or telemetry. The interactive page stores checklist progress in the browser's local storage.
- The zero-install viewer reads the JSON through the browser's local file picker. It does not upload the file and does not require a network connection.
- Source discovery and verification use the host agent's available web tools. The generated page is self-contained and does not fetch remote scripts; outbound resource links open only when you choose them.
- Terms, surrounding context, and search queries may be sent to the providers behind those host web tools during source discovery; review your host's data controls before researching sensitive material.
- The renderer validates the documented JSON structure, safely embeds JSON into HTML, treats supplied content as text, and only makes `http://` or `https://` resource links clickable.
- A resource is shown as verified only when the guide explicitly sets `verified: true`. “Verified” means the source was found and checked during research; it is not a guarantee that every claim remains current or that the source endorses the generated interpretation.
- Generated guides can contain your prompt fragments and research notes. Review them before sharing, and never put secrets in the input JSON.
- `--no-archive` is the opt-out for library writes. Without it, the renderer intentionally stores the JSON, HTML, and library index under the configured library path.

These controls reduce the risk of fabricated links, unsafe URL schemes, and HTML/script injection. They do not replace human review of research conclusions.

## Development

Edit the canonical skill only under `plugins/knowledge-compass/skills/knowledge-compass/`. Run the distribution check and the standard-library test suite before proposing a change:

```bash
python3 scripts/validate_distribution.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
claude plugin validate .claude-plugin/marketplace.json
claude plugin validate plugins/knowledge-compass
```

The distribution check and unit tests run in GitHub Actions on Python 3.8 and 3.12; run the Claude CLI validation locally when changing its manifests.

## License

[MIT](LICENSE) © 2026 hidetodong
