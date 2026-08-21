import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const template = fs.readFileSync(
  new URL("../src/template-dashboard-v1.3.0.html", import.meta.url),
  "utf8",
);
const helperBlock = template.match(
  /function esc\(value\) \{[\s\S]*?(?=\nfunction groupByTdt\()/,
)?.[0];
assert.ok(helperBlock, "应能提取项目概况渲染函数");

function render(weeklyAddition) {
  const context = {
    DATA: {
      dashboardYear: 2026,
      projectOverview: {
        enabled: true,
        total: 100,
        trackCount: 13,
        tracks: [{ key: "硬件系统", name: "硬件系统", label: "硬件系统", count: 10 }],
        productGenerations: [],
        weeklyAddition,
      },
      innovationCompetition: { enabled: false, projects: [] },
      developmentSummary: { enabled: false },
    },
    result: "",
  };
  vm.runInNewContext(`${helperBlock}\nresult = projectOverviewView();`, context);
  return context.result;
}

const sample = render({
  total: 6,
  tracks: [
    { label: "硬件系统", count: 3 },
    { label: "AI", count: 2 },
    { label: "通信", count: 1 },
  ],
  missingTrackCount: 0,
  missingTrackProjects: [],
  invalidCreatedTimeCount: 0,
  invalidCreatedTimeProjects: [],
});
assert.match(
  sample,
  /本周新增<strong>6<\/strong>个，其中硬件系统<strong>3<\/strong>个，AI<strong>2<\/strong>个，通信<strong>1<\/strong>个。/,
);
assert.doesNotMatch(sample, /硬件系统赛道|AI赛道|通信赛道/);

const noAddition = render({
  total: 0,
  tracks: [],
  missingTrackCount: 0,
  missingTrackProjects: [],
  invalidCreatedTimeCount: 0,
  invalidCreatedTimeProjects: [],
});
assert.doesNotMatch(noAddition, /本周新增/);
assert.doesNotMatch(noAddition, /weekly-addition-warning/);

const missingTrack = render({
  total: 2,
  tracks: [{ label: "硬件系统", count: 1 }],
  missingTrackCount: 1,
  missingTrackProjects: [{ code: "TDT-002", name: "缺赛道项目" }],
  invalidCreatedTimeCount: 0,
  invalidCreatedTimeProjects: [],
});
const missingSummary = missingTrack.match(
  /<p class="project-overview-summary">([\s\S]*?)<\/p>/,
)?.[1];
assert.ok(missingSummary);
assert.match(
  missingSummary,
  /本周新增<strong>2<\/strong>个，其中硬件系统<strong>1<\/strong>个。/,
);
assert.doesNotMatch(missingSummary, /未填写赛道/);
assert.match(missingTrack, /数据质量提醒/);
assert.match(missingTrack, /TDT-002 缺赛道项目/);

const allMissingTrack = render({
  total: 2,
  tracks: [],
  missingTrackCount: 2,
  missingTrackProjects: [
    { code: "TDT-003", name: "项目三" },
    { code: "", name: "项目四" },
  ],
  invalidCreatedTimeCount: 0,
  invalidCreatedTimeProjects: [],
});
const allMissingSummary = allMissingTrack.match(
  /<p class="project-overview-summary">([\s\S]*?)<\/p>/,
)?.[1];
assert.ok(allMissingSummary);
assert.match(allMissingSummary, /本周新增<strong>2<\/strong>个。/);
assert.doesNotMatch(allMissingSummary, /其中/);
assert.match(allMissingTrack, /TDT-003 项目三、项目四/);

console.log("weekly addition summary tests passed");
