# Demo2（列表＋详情面板）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有一键生成脚本上新增 demo2 版式——左侧 TDT＞子任务父子层级列表（收窄至 180px）＋右侧单项目详情（五个模块纵向堆叠、高亮条＋高亮块样式），并把里程碑标签 KO 更正为 TDR2。

**Architecture:** 数据层不变（`generate_dashboard.py` 输出同一份 DATA JSON），仅新增 `src/template-demo2.html` 模板；demo2 由 `--template … --variant demo2` 生成。KO→TDR2 属数据层标签修正，demo1/demo2 同步生效。

**Tech Stack:** Python 3（无第三方依赖）＋单文件 HTML（内联 CSS/JS，无外部资源）。

## Global Constraints

- 项目 AGENTS.md：Base URL 不硬编码进仓库；`output/` 与 `src/demo_scope.json` 不入库；改规范文档先于代码。
- 全局字体微软雅黑：`font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", system-ui, sans-serif`。
- 双配色 token 体系保持：Notion 纯白默认＋Claude 暖色可切换，深浅色经 `data-theme`/`data-palette` 组合，样式只允许引用 `var(--…)` token，不写死颜色。
- 所有来自 Base 的文本经模板内 `esc()` 转义后才进 innerHTML。
- 高亮条＝粗左边线（4px）＋浅色底＋加粗标题；高亮块＝浅色底＋细左边线（3px）＋右侧圆角（参考 CN6_H581 报告样式，用 token 实现）。
- 左侧边栏宽 180px（对比稿 240px 收窄 1/4）；子任务保持可点选；右侧本周进展/下周计划/风险描述各占独立一行。
- 生成命令的 Base URL 参数必须用 `'"…&…"'` 内嵌引号包裹（cmd.exe 的 `&` 坑）。
- Commit 信息中文、前缀 `feat:`/`chore:`，不加 Co-Authored-By。

**运行命令模板**（下文简称「生成 demo1/demo2」，`<Base URL>` 为含 `table`、`view` 参数的总表链接，由用户提供、不写入任何文件）：

```powershell
$env:PYTHONIOENCODING='utf-8'; & "D:\ai-workspace\shared\scripts\python.cmd" `
  "D:\ai-workspace\projects\01-project-status-dashboard\src\generate_dashboard.py" `
  --base-url '"<Base URL>"' `
  --lark-cli "C:\Users\siyuan.zhang\AppData\Roaming\npm\lark-cli.cmd" --as user
# demo2 追加：--template "D:\ai-workspace\projects\01-project-status-dashboard\src\template-demo2.html" --variant demo2
```

---

### Task 1: 里程碑标签 KO → TDR2（数据层，双版式生效）

**Files:**
- Modify: `projects/01-project-status-dashboard/src/generate_dashboard.py`（`build_project` 内 `build_milestone("KO", …)` 一行）

**Interfaces:**
- Produces: DATA JSON 中 `ms[2].lab == "TDR2"`（demo2 模板直接消费；demo1 模板无需改动，标签来自数据）。

- [ ] **Step 1: 修改标签**

`generate_dashboard.py` 中找到：

```python
            build_milestone("KO", record.get("TDR2(KO)", ""), record.get("TDR2实际", ""), run_date),
```

改为：

```python
            build_milestone("TDR2", record.get("TDR2(KO)", ""), record.get("TDR2实际", ""), run_date),
```

- [ ] **Step 2: 重新生成 demo1 验证**

运行「生成 demo1」命令（见 Global Constraints），期望：4 条「层级精确匹配成功」、无警告。

- [ ] **Step 3: 检查产物标签**

```powershell
$html = Get-Content "D:\ai-workspace\projects\01-project-status-dashboard\output\2026-07-11-tdt-dashboard-demo1.html" -Raw -Encoding UTF8; $html.Contains('"lab": "TDR2"'); $html.Contains('"lab": "KO"')
```

期望输出：`True` 然后 `False`。

- [ ] **Step 4: Commit**

```powershell
& "D:\ai-workspace\shared\scripts\git.cmd" add projects/01-project-status-dashboard/src/generate_dashboard.py
& "D:\ai-workspace\shared\scripts\git.cmd" commit -m "feat: 里程碑标签 KO 更正为 TDR2，demo1/demo2 数据层同步生效"
```

---

### Task 2: 创建 template-demo2.html（列表＋详情版式）

**Files:**
- Create: `projects/01-project-status-dashboard/src/template-demo2.html`（以 `template-demo1.html` 为底本改三处：头部去 PM 导航、主体 CSS 整段替换、渲染 JS 整段替换）

**Interfaces:**
- Consumes: DATA JSON（`groups[].pm / projects[].tdt,name,code,stage,risk,upd,cps,ms,week,next,riskDesc`），与 demo1 完全一致。
- Produces: 独立单文件模板，含 `/*__DATA__*/null` 占位符，供 `--template` 引用。

- [ ] **Step 1: 复制底本**

```powershell
Copy-Item "D:\ai-workspace\projects\01-project-status-dashboard\src\template-demo1.html" "D:\ai-workspace\projects\01-project-status-dashboard\src\template-demo2.html"
```

- [ ] **Step 2: 头部去掉 PM 导航（左列表本身就是导航）**

在 `template-demo2.html` 中删除 toolrow 里的两个元素（保留筛选 chips 容器）：

```html
      <span class="tool-sep"></span>
      <nav class="pm-nav" id="pm-nav"></nav>
```

并删除对应 CSS 规则块 `.tool-sep { … }`、`.pm-nav { … }`、`.pm-chip { … }`、`.pm-chip:hover { … }`（共四条规则）。

- [ ] **Step 3: 主体 CSS 整段替换**

删除从 `/* ============ 主体 ============ */` 起到 `footer {` 之前的全部规则（含 `.wrap`、`.pm-section`、`.pm-head`、`.pm-body`、`.card*`、`.grid-top`、`.cps`、`.tri` 及其媒体查询；保留 token 区、基础区、头部区、`.badge`、`.code`、`.ms*` 与 `footer`），插入：

```css
/* ============ 主体：列表 + 详情 ============ */
.layout {
  max-width: 1120px; margin: 0 auto; padding: 22px 24px 80px;
  display: grid; grid-template-columns: 180px 1fr; gap: 22px; align-items: start;
}

/* 左侧边栏：TDT > 子任务 父子层级 */
.sd {
  position: sticky; top: 100px; max-height: calc(100vh - 130px);
  overflow-y: auto; padding-right: 8px; border-right: 1px solid var(--line-soft);
}
.sd-pm { font-size: 11.5px; color: var(--muted); letter-spacing: .1em; margin: 12px 0 2px; }
.sd-tdt { font-size: 12px; font-weight: 600; color: var(--muted); margin: 10px 0 3px; line-height: 1.5; }
.sd-item {
  display: block; width: 100%; text-align: left; background: none; border: none;
  border-left: 2px solid var(--line); border-radius: 0 6px 6px 0;
  padding: 7px 8px 7px 11px; margin: 0 0 1px 4px; cursor: pointer;
  color: var(--ink); font: inherit; font-size: 13px; line-height: 1.45;
}
.sd-item:hover { background: var(--surface-2); }
.sd-item.active { background: var(--accent-soft); border-left-color: var(--accent); font-weight: 600; }
.sd-item .rk { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
.rk.hi { background: var(--risk-hi); } .rk.mid { background: var(--risk-mid); }
.rk.lo { background: var(--risk-lo); } .rk.none { background: var(--node-pend); }

/* 右侧详情 */
.dt-head { margin-bottom: 16px; }
.dt-tdt { font-size: 12.5px; color: var(--muted); margin-bottom: 4px; }
.dt-title { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.dt-name { font-size: 20px; font-weight: 700; }
.dt-title .upd { margin-left: auto; font-size: 11.5px; color: var(--muted); font-family: var(--mono); }
.dt-empty { color: var(--muted); padding: 60px 0; text-align: center; }

/* 模块：高亮条 + 高亮块（样式参考 CN6_H581 报告，token 化） */
.sec { margin: 0 0 18px; }
.sec-bar {
  font-size: 14px; font-weight: 600; color: var(--accent);
  border-left: 4px solid var(--accent); background: var(--accent-soft);
  padding: 6px 14px; border-radius: 0 4px 4px 0;
}
.sec-block {
  margin-top: 8px; background: var(--surface); border: 1px solid var(--line-soft);
  border-left: 3px solid var(--line); border-radius: 0 6px 6px 0;
  padding: 12px 16px; font-size: 14px;
}
.sec.risk .sec-bar { color: var(--risk-hi); border-left-color: var(--risk-hi); background: var(--risk-hi-bg); }
.sec.risk .sec-block { border-left-color: var(--risk-hi); background: var(--risk-hi-bg); border-color: transparent; }
.sec-block ul { margin: 0; padding-left: 20px; }
.sec-block li { margin-bottom: 6px; white-space: pre-wrap; }
.sec-block .risk-txt li { color: var(--risk-hi); }
.sec-block .none { color: var(--muted); margin: 0; }
.sec-block ol.cps-list { margin: 0; padding-left: 22px; line-height: 1.9; columns: 2; column-gap: 40px; }

@media (max-width: 760px) {
  .layout { grid-template-columns: 1fr; }
  .sd { position: static; max-height: none; border-right: none; }
  .sec-block ol.cps-list { columns: 1; }
}
```

- [ ] **Step 4: 渲染 JS 整段替换**

删除从 `/* 渲染看板 */` 起到 `/* 配色切换 */` 之前的全部 JS（含旧的看板渲染、PM 导航、分组折叠、风险筛选），并删除不再被引用的 `cardHtml`、`cpsHtml`、`pmStat` 三个函数（`esc`、`riskCls`、`msHtml`、`listHtml` 保留），插入：

```js
/* 渲染：左列表 + 右详情 */
document.getElementById("board").innerHTML =
  `<div class="layout"><nav class="sd" id="sd"></nav><main class="dt" id="dt"></main></div>`;

const ITEMS = [];
DATA.groups.forEach(g => g.projects.forEach(p => { p._i = ITEMS.length; p._pm = g.pm; ITEMS.push(p); }));

let filter = "all";
let current = ITEMS.length ? 0 : -1;

function matchFilter(p) { return filter === "all" || p.risk === filter; }

function sidebarHtml() {
  let html = "";
  DATA.groups.forEach(g => {
    const groupItems = g.projects.filter(matchFilter);
    if (!groupItems.length) return;
    html += `<div class="sd-pm">${esc(g.pm)}</div>`;
    const byTdt = new Map();
    groupItems.forEach(p => {
      const key = p.tdt || "未指定TDT";
      if (!byTdt.has(key)) byTdt.set(key, []);
      byTdt.get(key).push(p);
    });
    byTdt.forEach((list, tdt) => {
      html += `<div class="sd-tdt">${esc(tdt)}</div>`;
      list.forEach(p => {
        html += `<button class="sd-item" data-i="${p._i}">
          <span class="rk ${riskCls(p.risk)}"></span>${esc(p.name)}</button>`;
      });
    });
  });
  return html;
}

function buildSidebar() {
  document.getElementById("sd").innerHTML = sidebarHtml();
  document.querySelectorAll(".sd-item").forEach(b =>
    b.addEventListener("click", () => { current = +b.dataset.i; renderDetail(); }));
}

function cpsBlock(cps) {
  if (!cps || !cps.length) return `<p class="none">—</p>`;
  return `<ol class="cps-list">${cps.map(c => `<li>${esc(c)}</li>`).join("")}</ol>`;
}

function renderDetail() {
  const dt = document.getElementById("dt");
  const p = ITEMS[current];
  if (!p) { dt.innerHTML = `<div class="dt-empty">当前筛选下没有项目</div>`; return; }
  const secs = [
    { t: "里程碑", b: msHtml(p.ms) },
    { t: `控制点 · ${(p.cps || []).length} 项`, b: cpsBlock(p.cps) },
    { t: "本周进展", b: listHtml(p.week) },
    { t: "下周计划", b: listHtml(p.next) },
    { t: "风险描述", b: listHtml(p.riskDesc, "risk-txt"), cls: (p.riskDesc && p.riskDesc.length) ? "risk" : "" },
  ];
  dt.innerHTML = `
    <div class="dt-head">
      <div class="dt-tdt">TDT · ${esc(p.tdt || "—")}　·　${esc(p._pm)}</div>
      <div class="dt-title">
        <span class="dt-name">${esc(p.name)}</span><span class="code">${esc(p.code)}</span>
        <span class="badge stage">${esc(p.stage)}</span><span class="badge ${riskCls(p.risk)}">${esc(p.risk)}</span>
        ${p.upd ? `<span class="upd">更新 ${esc(p.upd)}</span>` : ""}
      </div>
    </div>` +
    secs.map(s => `<section class="sec ${s.cls || ""}">
      <div class="sec-bar">${s.t}</div><div class="sec-block">${s.b}</div></section>`).join("");
  document.querySelectorAll(".sd-item").forEach(b =>
    b.classList.toggle("active", +b.dataset.i === current));
}

/* 风险筛选：过滤左列表；当前项被滤掉时自动切到第一个可见项 */
document.querySelectorAll(".chip[data-f]").forEach(chip => chip.addEventListener("click", () => {
  document.querySelectorAll(".chip[data-f]").forEach(c => c.classList.remove("active"));
  chip.classList.add("active");
  filter = chip.dataset.f;
  buildSidebar();
  const visible = ITEMS.filter(matchFilter).map(p => p._i);
  if (!visible.includes(current)) current = visible.length ? visible[0] : -1;
  renderDetail();
}));

buildSidebar();
renderDetail();
```

- [ ] **Step 5: 静态自检（占位符与残留）**

```powershell
$t = Get-Content "D:\ai-workspace\projects\01-project-status-dashboard\src\template-demo2.html" -Raw -Encoding UTF8
$t.Contains('/*__DATA__*/null'); $t.Contains('sec-bar'); $t.Contains('sd-item')
$t.Contains('pm-nav'); $t.Contains('cardHtml'); $t.Contains('grid-top'); $t.Contains('pmStat')
```

期望输出：前三个 `True`，后四个 `False`。

- [ ] **Step 6: Commit**

```powershell
& "D:\ai-workspace\shared\scripts\git.cmd" add projects/01-project-status-dashboard/src/template-demo2.html
& "D:\ai-workspace\shared\scripts\git.cmd" commit -m "feat: 新增 demo2 模板（列表+详情面板，高亮条/高亮块模块化版式）"
```

---

### Task 3: 生成 demo2 并验证

**Files:**
- 产出（不入库）：`output/2026-07-11-tdt-dashboard-demo2.html` 与同名 `.report.json`

**Interfaces:**
- Consumes: Task 1 的脚本（TDR2 标签）＋ Task 2 的模板。

- [ ] **Step 1: 生成 demo2**

运行「生成 demo2」命令（Global Constraints 中的命令追加 `--template …template-demo2.html --variant demo2`）。
期望：4 条「层级精确匹配成功」、零警告、产物路径以 `-demo2.html` 结尾。

- [ ] **Step 2: 产物数据与结构检查**

```powershell
$html = Get-Content "D:\ai-workspace\projects\01-project-status-dashboard\output\2026-07-11-tdt-dashboard-demo2.html" -Raw -Encoding UTF8
$html.Contains('"lab": "TDR2"'); $html.Contains('sec-bar'); $html.Contains('sd-item'); $html.Contains('"tdt": "印度5.5G通信"')
```

期望输出：四个 `True`。

- [ ] **Step 3: 浏览器人工验收（用户执行）**

打开 `output/2026-07-11-tdt-dashboard-demo2.html` 核对：左栏 180px 且 TDT＞子任务层级清晰、子任务可点选切换；右侧五个模块（里程碑/控制点/本周进展/下周计划/风险描述）纵向各占一行、高亮条＋高亮块样式生效、有风险的项目风险模块红色调；风险筛选正确过滤左栏并自动切换选中项；双配色与深浅色切换正常；无横向滚动。

- [ ] **Step 4: 同步文档并提交**

`README.md` Demo 版式表中 demo2 行改为：

```markdown
| demo2 | `src/template-demo2.html` | 方案 C：列表＋详情面板（TDT＞子任务侧栏，五模块高亮条/块） |
```

`ROADMAP.md`：「后续事项」中 demo2 一条移入「已完成」（注明日期与验证结论），「最近验证」补一行生成与核对记录。

```powershell
& "D:\ai-workspace\shared\scripts\git.cmd" add projects/01-project-status-dashboard/README.md projects/01-project-status-dashboard/ROADMAP.md
& "D:\ai-workspace\shared\scripts\git.cmd" commit -m "docs: 登记 demo2（列表+详情面板）完成与验证记录"
```
