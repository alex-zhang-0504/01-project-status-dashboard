import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = relativePath => fs.readFileSync(path.join(projectRoot, relativePath), "utf8");
const template = read("src/template-dashboard-v1.3.0.html");
const meetingContent = JSON.parse(read("src/meeting_content.json"));
const pieSample = read("docs/samples/pie-chart.html");
const readme = read("README.md");

assert.match(template, /<title>TDT 技术项目状态看板 · V1\.3\.0<\/title>/);
assert.match(template, /<h1>TDT 技术项目状态看板 V1\.3\.0<\/h1>/);
assert.doesNotMatch(template, /V1\.[01]\.0/);

assert.match(template, /--accent:\s*#0a9bf5;/i);
assert.match(template, /--ink:\s*#363636;/i);
assert.match(template, /--table-font-size:\s*16px;/);
assert.match(template, /--table-head-weight:\s*700;/);
assert.match(template, /--table-body-weight:\s*400;/);
assert.doesNotMatch(template, /--table-font-size:\s*17px;/);
assert.doesNotMatch(template, /@font-face|<link\b/i);
assert.doesNotMatch(template, /#board,\s*#board\s*\*\s*\{/);

const boardTypography = template.match(/^#board\s*\{([\s\S]*?)\n\}/m)?.[1];
assert.ok(boardTypography, "看板根节点应保留基础字体兜底");
assert.match(boardTypography, /font-size:\s*13px;/);
assert.match(boardTypography, /font-weight:\s*400;/);

const pmSummaryStyles = template.match(/#board \.pm-summary\s*\{([\s\S]*?)\n\}/)?.[1];
assert.ok(pmSummaryStyles, "PM 摘要应有独立字体规则");
assert.match(pmSummaryStyles, /font-size:\s*var\(--table-font-size\);/);
assert.match(pmSummaryStyles, /font-weight:\s*var\(--table-body-weight\);/);
assert.match(template, /#board \.pm-summary h2\s*\{[^}]*font-size:\s*inherit;[^}]*font-weight:\s*inherit;/);

const emptyStateStyles = template.match(/#board \.board-empty\s*\{([\s\S]*?)\n\}/)?.[1];
assert.ok(emptyStateStyles, "视图空态应有独立字体规则");
assert.match(emptyStateStyles, /font-size:\s*var\(--table-font-size\);/);
assert.match(emptyStateStyles, /font-weight:\s*var\(--table-body-weight\);/);
assert.match(template, /#board \.chart-axis-line span\s*\{[\s\S]*?font-size:\s*13px;/);
assert.match(readme, /九字段 Numbers 风格连续表格/);
assert.doesNotMatch(readme, /九字段卡片式表格|九字段卡片行|所有表格及卡片式表格/);

const copyrightStyles = template.match(/\.copyright-mark\s*\{([\s\S]*?)\n\}/)?.[1];
assert.ok(copyrightStyles, "应保留右下角版权标识样式");
assert.match(copyrightStyles, /font-size:\s*12px;/);
assert.doesNotMatch(copyrightStyles, /font-size:\s*11px;/);
assert.match(template, />Designed by Siyuan for TRD<\/div>/);

const overviewYearStyles = template.match(/\.project-overview-year\s*\{([\s\S]*?)\n\}/)?.[1];
assert.ok(overviewYearStyles, "项目概况年份应有独立样式");
assert.match(overviewYearStyles, /color:\s*var\(--accent\);/);
assert.match(template, /DATA\.dashboardYear/);
assert.match(template, /const overviewYear = Number\.isInteger\(dashboardYear\)\s*\? `<span class="project-overview-year">\$\{dashboardYear\}年<\/span>`\s*: "";/);
assert.match(template, /\.weekly-addition-warning\s*\{/);
assert.match(template, /weeklyAddition/);
assert.doesNotMatch(template, /2026年TDT项目价值概况|2026年截至本周|2026年截止本周|2026年TDT项目子任务开发达成概况|2026年截至目前/);

assert.match(template, /中风险＋高风险＋延期＋fail/);
assert.match(template, /延期＝\$\{riskCounts\.delayed \|\| 0\}，fail＝\$\{riskCounts\.fail \|\| 0\}/);
assert.match(template, /项目状态中分别包含「延期」／「fail」的记录/);
assert.match(template, /同一项目状态同时包含两词时，分别计入公式分子的对应项/);
assert.doesNotMatch(template, /状态同时包含「开发完成」和「fail」时/);

assert.match(template, /\.chart-axis\s*\{/);
assert.match(template, /\.chart-axis-line\s*\{/);
assert.match(template, /chartAxisHtml\(trackScale\)/);
assert.match(template, /chartAxisHtml\(generationScale\)/);

const chartScaleSource = template.match(/function chartScale\(max\) \{[\s\S]*?\n\}/)?.[0];
assert.ok(chartScaleSource, "应保留 chartScale() 图表刻度函数");
const chartScale = new Function(`"use strict"; ${chartScaleSource}; return chartScale;`)();
assert.deepEqual(chartScale(1).ticks, [0, 1]);
assert.deepEqual(chartScale(2).ticks, [0, 1, 2]);
for (const max of [0, 1, 2, 3, 5, 9, 92]) {
  const scale = chartScale(max);
  assert.equal(scale.ticks[0], 0, `max=${max} 的纵轴必须从 0 开始`);
  assert.ok(scale.top >= Math.max(max, 1), `max=${max} 的顶刻度不能低于数据`);
  for (let index = 1; index < scale.ticks.length; index += 1) {
    assert.ok(scale.ticks[index] - scale.ticks[index - 1] >= 1, `max=${max} 不得出现小于 1 的刻度步长`);
  }
}

assert.doesNotMatch(template, /孟跃龙|朱荣昌/);
assert.doesNotMatch(template, /meeting-discipline-template/);
assert.match(template, /function meetingDisciplineView\(\)/);
assert.equal(meetingContent.sections[0].title, "会议纪律");
assert.equal(meetingContent.sections[0].items.length, 2);
assert.equal(meetingContent.sections[1].items.length, 7);
assert.match(JSON.stringify(meetingContent), /孟跃龙/);
assert.match(JSON.stringify(meetingContent), /朱荣昌/);
assert.doesNotMatch(template, /示例审批人|示例收款人/);

const meetingTitleStyles = template.match(/#board \.meeting-title\s*\{([\s\S]*?)\n\}/)?.[1];
const meetingItemStyles = template.match(/#board \.meeting-item\s*\{([\s\S]*?)\n\}/)?.[1];
assert.ok(meetingTitleStyles, "会议纪律标题应保留独立样式");
assert.match(meetingTitleStyles, /font-size:\s*24pt;/);
assert.match(meetingTitleStyles, /font-weight:\s*700;/);
assert.ok(meetingItemStyles, "会议纪律正文应保留独立样式");
assert.match(meetingItemStyles, /font-size:\s*15pt;/);
assert.match(template, /#board \.meeting-item \* \{ font-size: 15pt; \}/);
assert.match(template, /\.meeting-marker \{[^}]*color: var\(--ink\);/);
assert.match(template, /#board \.meeting-part\.danger \{ color: var\(--risk-hi\); font-weight: 700; \}/);
assert.match(template, /#board \.meeting-part\.accent \{ color: var\(--accent\); font-weight: 700; \}/);

const meetingRendererSource = template.slice(
  template.indexOf("function meetingPartHtml(part)"),
  template.indexOf("function issueStatusClass(status)"),
);
assert.ok(meetingRendererSource, "应保留会议内容数据渲染函数");
const meetingRenderer = new Function(
  "DATA",
  "esc",
  `${meetingRendererSource}; return meetingDisciplineView();`,
);
const meetingHtml = meetingRenderer(
  { meetingDiscipline: { enabled: true, sections: meetingContent.sections } },
  value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]),
);
assert.equal((meetingHtml.match(/class="meeting-title"/g) || []).length, 2);
assert.equal((meetingHtml.match(/class="meeting-item"/g) || []).length, 9);
assert.match(meetingHtml, /class="meeting-part danger">500元\/次<\/span>/);
assert.match(meetingHtml, /class="meeting-part accent">孟跃龙<\/span>/);
assert.match(meetingHtml, /class="meeting-marker" aria-hidden="true">■<\/span>/);

assert.match(pieSample, /--ink:\s*#363636;\s*--muted:\s*#787878;/i);
assert.match(pieSample, /--table-rule:\s*#b8b8b8;/i);
assert.match(pieSample, /--chart-cat-5:\s*#8e8e8e;/i);
assert.match(pieSample, /\.\.\/\.\.\/design\.md 第 5 节/);

console.log("template design regression checks passed");
