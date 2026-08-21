import assert from "node:assert/strict";
import fs from "node:fs";

const template = fs.readFileSync(new URL("../src/template-dashboard-v1.3.0.html", import.meta.url), "utf8");
const scriptBlocks = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
assert.equal(scriptBlocks.length, 2, "正式模板应包含两个内嵌脚本");
scriptBlocks.forEach(source => new Function(source));
assert.doesNotMatch(template, /EMPTY_CELL_PLACEHOLDERS/);
const riskClassBlock = template.match(/const RISK_CLS = \{[^\n]+\};/)?.[0];
const helperBlock = template.match(/function esc\(value\) \{[\s\S]*?(?=\nfunction projectOverviewView\(\))/)?.[0];
const taskRowBlock = template.match(/function taskRow\(project\) \{[\s\S]*?(?=\nfunction tdtSection\(tdt\))/)?.[0];
const issueRowBlock = template.match(/function issueRow\(issue\) \{[\s\S]*?(?=\nfunction issueTable\(group\))/)?.[0];

assert.ok(riskClassBlock, "未找到风险徽章映射");
assert.ok(helperBlock, "未找到表格空值渲染函数");
assert.ok(taskRowBlock, "未找到详细进展表格行函数");
assert.ok(issueRowBlock, "未找到遗留问题表格行函数");

const loadRenderers = new Function(`${riskClassBlock}\n${helperBlock}\n${taskRowBlock}\n${issueRowBlock}; return {
  cellText, listHtml, textHtml, issueTaskHtml, peopleHtml, taskRow, issueRow
};`);
const { cellText, listHtml, textHtml, issueTaskHtml, peopleHtml, taskRow, issueRow } = loadRenderers();

for (const value of [null, undefined, "", "   "]) {
  assert.equal(cellText(value), "");
  assert.equal(textHtml(value), "");
}
for (const [value, expected] of [
  ["/", "/"], [" / ", "/"], ["／", "／"], ["-", "-"], ["--", "--"],
  ["—", "—"], ["–", "–"], ["未填写", "未填写"], ["暂无", "暂无"], ["无", "无"]
]) {
  assert.equal(cellText(value), expected);
  assert.equal(textHtml(value), expected);
}
assert.equal(cellText(0), "0");
assert.equal(cellText(false), "false");
assert.equal(cellText("A/B"), "A/B");
assert.equal(textHtml("正文 / 内容"), "正文 / 内容");
assert.equal(textHtml("暂无结论"), "暂无结论");
assert.equal(listHtml([]), "");
assert.match(listHtml(["/", "  "]), /<li>\/<\/li>/);
assert.match(listHtml(["A/B"]), />A\/B</);
assert.match(issueTaskHtml("/"), />\/<\/div>/);
assert.equal(peopleHtml("/"), "/");
assert.equal(peopleHtml("／"), "／");
assert.equal(peopleHtml("张三/"), "张三/");
assert.equal(peopleHtml("张三/李四"), "张三<br>李四");

const emptyTaskRow = taskRow({
  name: "任务A/B",
  code: "",
  valueDecision: "",
  closeDate: "",
  risk: "",
  stage: "",
  cps: [],
  week: [],
  next: [],
  riskDesc: [],
});
assert.equal(emptyTaskRow.includes(">/</"), false);
assert.doesNotMatch(emptyTaskRow, /class="badge/);
assert.match(emptyTaskRow, /任务A\/B/);
assert.equal((emptyTaskRow.match(/role="cell"/g) || []).length, 9);

const literalTaskRow = taskRow({
  name: "未填写",
  code: "/",
  valueDecision: "—",
  closeDate: "暂无",
  risk: "/",
  stage: "无",
  cps: ["/"],
  week: ["-"],
  next: ["--"],
  riskDesc: ["／"],
});
assert.match(literalTaskRow, /class="badge none">\/<\/span>/);
for (const value of ["未填写", "—", "暂无", "无", "-", "--", "／"]) {
  assert.equal(literalTaskRow.includes(value), true);
}

const emptyIssueRow = issueRow({
  item: "",
  taskName: "",
  task: "",
  progress: "",
  plannedDate: "",
  adjustedDate: "",
  actualDate: "",
  proposer: "",
  department: "",
  owner: "",
  status: "",
});
assert.equal(emptyIssueRow.includes(">/</"), false);
assert.doesNotMatch(emptyIssueRow, /class="issue-status/);
assert.equal((emptyIssueRow.match(/<td(?:\s|>)/g) || []).length, 11);

assert.match(template, /Array\.from\(\{ length: 11 \}, \(\) => "<td><\/td>"\)/);
for (const field of ["name", "track", "stage", "status", "risk"]) {
  assert.match(template, new RegExp(`<td>\\$\\{textHtml\\(project\\.${field}\\)\\}<\\/td>`));
}
console.log("empty table cell tests passed");
