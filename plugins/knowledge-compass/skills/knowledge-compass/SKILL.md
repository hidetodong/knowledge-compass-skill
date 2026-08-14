---
name: knowledge-compass
description: This skill should be used when the user has a handful of scattered, unfamiliar terms or jargon they ran into somewhere and wants to figure out what field they belong to, where the authoritative/trustworthy knowledge on that field lives, and how to start learning it — e.g. "我最近老听到 X、Y、Z 这几个词，不知道是什么领域", "these buzzwords keep coming up, what domain is this and how do I get into it", "reverse-engineer the field from these terms and give me a learning roadmap", "这些名词属于哪个领域？有哪些权威资料和学习路径". It reverse-infers the domain from the terms (confirming candidates with the user when ambiguous), deep-researches verified authoritative sources, and produces a richly layered, source-verified learning path rendered as a self-contained interactive webpage and archived into a personal library. Trigger even when the user doesn't say "domain", "field", or "learning path" — any time they have orphan terminology and want to know the field plus where to learn it authoritatively.
license: MIT
metadata:
  version: "0.5.0"
  author: "hidetodong"
  compatibility: "Python 3.8+; Claude Code; Codex"
---

# Knowledge Compass · 知识罗盘

## Overview

把零星、看不懂的几个名词，变成三样东西：(1) 它们属于的**领域**，(2) 这个领域**经核实的权威知识来源**，(3) 一条**分层、可执行的学习路径**——最终渲染成一个自包含的交互网页，并归档进一个可长期回看的领域库。

最难的部分是**不编造来源**：任何一本书、一篇论文、一门课、一个站点，进入成品前都必须先核实它真实存在。一个"自信但错误"的来源比直接不写更糟。

## 输出语言与呈现（中文为主，绝不留谜语）

成品**以中文为主**，并遵守两条硬规则——它们直接决定读者能不能看懂：

- **英文标题中英对照，中文在前**：每个英文资源都给中文译名 + 括注原名，例如 `《信息论基础》（Elements of Information Theory）`、`《概率导论》（Introduction to Probability）`。只有原名、没有中文，读者就得自己猜。
- **不留看不懂的缩写**：首次出现的缩写一律展开或解释，例如 `KL 散度（相对熵）`、`大数定律（Law of Large Numbers）`。一个孤零零的缩写会让非专业读者直接卡住。

这两条不是排版洁癖——这个 skill 的用户往往正是该领域的门外汉（所以才需要罗盘），任何没解释的术语都是一道墙。

## When to use

- 用户列出一堆碰到的术语 / buzzword，问这是什么领域。
- 用户已知领域，但想要这个领域的**权威经典 + 学习路线**。
- 用户手里有"无主的名词"，想被指向可信来源——哪怕他从没说过"领域""学科""学习路径"这些字眼。

## Workflow

整个流程刻意分两段：先用便宜的"解码"过一遍并**让用户确认**，再把昂贵的深度研究只花在确认过的领域上。

### Phase 0 — Intake（收集碎片）
收齐用户手里的每个术语，以及任何上下文（在哪听到的、旁边还有什么词）。一个词也能起步，但更多词能更好地三角定位——如果只给了一个含糊的词，先问问还有没有别的词或语境再开研究。但别过度阻塞，用户实在没有就继续。

### Phase 1 — Decode candidate domains, then confirm（解码候选领域，然后确认）
1. 用网络搜索（必要时配百科 / 维基）研究这些词。对每个词，记下它出现在哪些领域。**最关键的信号是共现**：正确的领域是这些词被**一起**使用的那个，而不只是各自单独出现的地方。
2. 把词聚类，找它们共同的母领域。警惕：跨领域的同形词（一个词在物理和金融里意思不同）、子专业 vs 母领域、伪装成概念的产品 / 品牌名、不合群的噪声词。
3. 产出 **1–3 个候选领域**。每个给出：名称、一句话范围、哪些词指向它、置信度（高 / 中 / 低）、以及哪些词**不吻合**（可能意味着领域更窄、不同，或某个词是噪声）。
4. **确认门。** 紧凑地把候选呈现给用户——一个简短带标签的列表（领域 — 置信度 — 哪些词指向它），不要长篇大论——请用户确认或收窄，再进入深度研究。如果只有一个高置信领域、每个词都干净吻合，那就用一行陈述结论、请用户快速点头即可，别强行制造一个无意义的选择——但**仍要等确认**再进 Phase 2。这道门是避免研究错领域的最便宜的防线。

### Phase 2 — Deep-research the confirmed field（深度研究确认后的领域）
先把领域的"地形"摸清楚，再按下面的类别收集权威来源。若有子代理（subagent）可用，把各类别并行铺开以提速、提全。

- **领域的形态**：定义、范围、主要子方向、相邻领域 / 边界，以及它是成熟的经典体系还是活跃的前沿（这会改变"什么算权威"）。
- **要收集的权威来源**（这四类要在分层里都覆盖到）：
  - **教材 / 参考书**：从业者真正引用的标准教材、经典参考。
  - **奠基 / 里程碑论文**：研究驱动的领域尤其重要。
  - **权威课程**：大学公开课、真实机构出品的高质量在线课。
  - **标准 / 官方机构 / 社区**：领域有的话——标准组织、关键人物 / 实验室 / 机构、顶级会议 / 期刊、官方文档 / 权威站点。

**权威性准则（authority rubric）**——优先 一手 > 二手 > 三手；偏向领域自身引用的东西（经典、奠基论文、标准机构、顶级场所）和公认专家 / 机构，而非匿名博客。拒绝 SEO 内容农场、清单体、AI 拼凑的综述。快速演进的领域看重时效；成熟经典看重地位。

**反幻觉纪律（第一纪律，不可妥协）。** 每个写进成品的来源都要经搜索 / 抓取核实，并附上真实 URL 或稳定标识（ISBN / DOI）。只有核实通过后才能显式标 `verified: true`；无法确认存在的，要么删掉，要么显式标 `verified: false` 并在 `verify_note` 写明原因（字段缺失也会被网页按 ⚠ 未核实处理）。**绝不**把"凭记忆想起来的"来源当权威呈上。

### Phase 3 — Synthesize the layered guide（综合成分层学习指南）
把研究结果组织成一份**丰富、分层**的领域指南，写成一个 JSON 对象（schema 见 `scripts/view_field_guide.py` 顶部，也概述于下文"内容规范"）。这一份 JSON 就是**唯一真相源**——网页只是渲染它。

分层不是把来源堆成一坨，而是给读者一条**有坡度的路**：

- 🌱 **入门**——建立直觉 / 打基础　📘 **经典**——领域公认的核心读物　🚀 **进阶**——深入 / 研究导向　🛠 **实践 / 课程**——公开课、可视化、动手工具
- **每一层放 2–4 个来源**，并按优先级标注：`必读`（绕不开）/ `推荐`（很好的补充）/ `可选`（按需取用）。网页会据此给徽章、左边框配色，并把必读自动排在前面。
- 每个来源都尽量给齐：中英对照的标题、作者 / 版本 / 年份、类型、**为什么权威 / 为什么在这一层**（reason）、读它需要的**前置**、**难度**、**适合谁**、链接、是否免费、核实状态。
- 顶层还要给：**领域眉题**（`domain`，见下）、领域判断一行（哪些碎片共现锁定该领域）+ 置信度、横跨的**学科归属**、2–4 句**领域速览**、整个领域的**前置知识**（学这块整体需要先会什么）。
- 最后给一份**分阶段学习计划**（plan）：每个阶段说清「读哪些资源的哪部分、目标、达到什么标志可进下一阶段」，并尽量标个大致周期。网页会把它渲染成可勾选、带进度记忆的时间线。

再做三件事，让成品**点明领域、可溯来源、可看依赖**：

- **标题直接点明领域**（不要泛泛）。`topic` 一律以反推出的**领域 + 分支**领衔，并填 `domain` 眉题——网页会把它渲染成大标题上方的醒目金色眉题。例如碎片是「集体表象、社会事实、失范」，就不是写「集体表象」，而是 `domain: "社会学 · 古典社会学理论"`、`topic: "涂尔干学派：集体表象与社会事实"`。读者第一眼就知道这是哪个学科。
- **引用要可溯**（绑定反幻觉，第一纪律的延伸）。凡正文里的**分析性结论**——领域速览、领域判断、某来源"为什么权威"、前置判断——只要是从某个出处得来的，就在该处写 `[1]`、`[2]` 角标，并在顶层 `references` 数组里按序登记出处（`title` / `source` / `url` / 可选 `note`）。网页把它们渲染成页面**最下方的编号「参考来源」区**，角标可点击跳转。这让"这个判断从哪来"一查即知，而不是凭空断言。`references` 里的出处同样适用反幻觉纪律：核实存在才登记。
- **资源有先后就给依赖**（驱动流程树）。当来源之间存在明确的**学习先后**（要先读完 A 才啃得动 B）时，给每个相关来源一个稳定 `id`，并在后置来源上填 `requires: [前置的 id, …]`。网页据此提供「📚 分层视图 / 🌳 学习路线树」切换：树里按依赖分层、画连线箭头（顶层=可任意起步）。注意 `requires`（资源→资源依赖）与 `prereq`（该来源需要的背景知识，自由文本）是两回事，别混填。没有清晰先后关系就别硬造——不填 `requires`，切换按钮就不出现。

### Phase 4 — View it now, and archive it for later（即看，并归档以备回看）
把 JSON 交给自带的渲染脚本。它做两件事：给用户**这一份**指南的交互网页，并把它**归档进一个中央库**，方便日后回看所有解码过的领域。

```bash
python3 "<skill-dir>/scripts/view_field_guide.py" <guide.json>
```

运行前先把 `<skill-dir>` 解析为本文件 `SKILL.md` 所在目录：Claude Code 插件中可用 `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-compass`；Codex 和 Pi 使用宿主提供的本 skill 文件路径。无法确认目录时停止，不猜路径。

**即看。** 脚本把 JSON 内联进 `assets/viewer_template.html`，写出一个自包含的 `.html`（数据全在文件里，无需服务器、好保存、好分享），然后在本地浏览器打开：顶部是领域判断 + 置信度 + 学科，每个来源是一张带 ✓已核实 / ⚠未核实 徽章和可点链接的卡片，学习计划是一条进度存在浏览器里的可勾选时间线。

**归档以备回看（一个产物目录，全在一处）。** 它把这份指南的 `.json` 源 + `.html` 页 + 重建的 `index.html` 统一放进**一个产物目录**（即"库"）。库位置由环境变量 `KNOWLEDGE_COMPASS_LIBRARY` 配置（也可 `--library DIR` 临时覆盖），未配置时回落默认 `~/knowledge-compass/`。HTML、JSON、index 三者**始终同处一目录**，不再散落。`index.html` 是一页总览，列出过往每一份指南（领域、置信度、日期、未核实数）——所以**回看过往研究 = 打开库里的 `index.html` 点卡片**。把库指到云同步文件夹（如 Google Drive 桌面同步目录），就零成本拿到云端归档 + 跨设备回看。

**唯一真源就在库里，改它重跑即就地刷新。** `.json` 是唯一真相源，网页只渲染它。**当传入的 JSON 已在库内**（推荐：直接在产物目录里编辑那一份），脚本就**就地渲染**——在它旁边写同名 `.html`、把 JSON 回写自身，**不再另起 `<date>-<slug>` 副本**：于是一份指南只有一份 JSON，改它重跑只是幂等刷新，不会散出游离的工作副本。**库外的 JSON** 首次运行会以 `<date>-<领域slug>` 归档进库、建立规范名；同名产物已存在时会追加数字后缀，避免静默覆盖。此后就编辑库内那份、重跑它即可。在无显示 / headless 环境里脚本检测到 SSH/mosh 会自动只打印路径不强开。常用参数：`--out PATH`（把 HTML 写到别处）、`--library DIR`（换库位置）、`--no-archive`（不归档、不重建索引；默认在输入 JSON 旁输出）、`--no-open`（只写文件、不开浏览器）。

## 内容规范（JSON 怎么填）

完整字段见 `scripts/view_field_guide.py` 顶部 docstring。要点：

- **顶层**：`topic`（标题，以领域+分支领衔，如「涂尔干学派：集体表象与社会事实」）、`domain`（领域眉题，如「社会学 · 古典社会学理论」，渲染成大标题上方金色眉题）、`fragments`（用户原始碎片，原样照列）、`domain_judgment`（一行——哪些词共现锁定该领域）、`confidence`（高/中/低）、`excluded`（可选，被排除 / 不吻合的词；全吻合则省略）、`disciplines`（学科归属数组）、`overview`（2–4 句速览）、`prerequisites`（领域级前置）。正文字段（`overview`/`domain_judgment`/`excluded`/`prerequisites` 及各 `reason`/`plan.detail`/`route`）里可写 `[n]` 角标引用 `references`。
- **`layers`**：每层 `{emoji, title, subtitle, resources[]}`；4 层（入门 / 经典 / 进阶 / 实践），每层 2–4 个来源。
- **每个 resource**：`name`（中英对照）、`meta`（作者，版本/年份）、`type`、`priority`（必读/推荐/可选）、`prereq`（背景知识，自由文本）、`reason`、`difficulty`、`audience`、`url`（仅 `http://` / `https://`）、`free`、`verified`（只有显式 `true` 才显示已核实）、`verify_note`；流程树相关：`id`（1–64 位小写字母、数字、`.`、`_`、`-` 组成的稳定键；不要用 `constructor` / `prototype` 等保留键）、`requires`（前置来源 id 数组，资源→资源依赖，与 `prereq` 不同）。
- **`references`**：可溯出处数组 `{title, source, url, note}`，按序号对应正文 `[n]` 角标，渲染在页面最下方「参考来源」区；登记前同样须核实存在。
- **`plan`**：分阶段数组 `{step, detail}`，可执行、有目标和完成标志；没有 plan 时才用 `route`（一段话替代）。

**一个 resource 的示例：**

```json
{"name": "《概率导论》（Introduction to Probability，第 2 版）",
 "meta": "Joseph K. Blitzstein & Jessica Hwang · Chapman & Hall/CRC，2019",
 "id": "intro-prob", "requires": ["calculus"],
 "type": "教材", "priority": "必读", "prereq": "微积分",
 "reason": "哈佛 Stat 110 的配套书，直觉与严谨平衡极好，全书免费且有公开课视频[1]。",
 "difficulty": "入门友好", "audience": "想系统自学的零基础者",
 "url": "https://probabilitybook.net", "free": true, "verified": true}
```

**对应的 `references`（正文 `[1]` 链到这里）：**

```json
"references": [
  {"title": "Stat 110: Probability（哈佛公开课主页）", "source": "Joseph K. Blitzstein · 哈佛大学",
   "url": "https://stat110.hsites.harvard.edu", "note": "课程与配套书免费开放"}
]
```

## Notes

- **别跳过 Phase 1 的确认门**——在深度研究前确认领域，是对"整份报告全错"最便宜的防御。
- **核实重于数量**：一小批真实、权威的来源，胜过一长串掺了未核实条目的清单。
- **每层 2–4 个、覆盖四类来源**：太少显得单薄，太多读者会迷路；优先级（必读/推荐/可选）就是帮读者在多个来源里分清主次。
- 如果这些词其实出自骗局、营销造词、或并不存在的"领域"，**如实说**，而不是为它编一套经典。
- 一个词就能起步，但永远优先要更多词 / 语境来三角定位。
