---
name: siyuan-refresh-tdt-stage-snapshot
description: "Use when the user provides a Feishu/Lark Base URL for the 01-project-status-dashboard TDT project table and wants to preview, create, check, or recover a weekly stage snapshot before refreshing or importing 「阶段查找」. Keywords: TDT, 阶段查找, 上周阶段快照, 阶段快照日期, Base, 多维表格."
---

# TDT 阶段快照刷新

> 当前状态：暂时停用，阶段快照由部门专人手工处理。后续如重新启用，必须先在目标总表中增加「阶段快照日期」字段，并按本文既有流程重新预检；Skill 的触发条件、执行流程和脚本暂不改动。

把多维总表中全部子任务的「阶段查找」保存到「上周阶段快照（自动维护）」，并写入统一的「阶段快照日期」。只执行这一项维护，不生成看板，不修改其他字段。

## TRIGGER / SKIP

TRIGGER：用户提供 01-project-status-dashboard 项目的飞书多维表格 URL，并要求在刷新或导入「阶段查找」前，预检、创建、检查或恢复 TDT 周度阶段快照。

SKIP：看板生成或刷新；「阶段查找」已经刷新后再覆盖本周快照；其他项目或其他 Base 的阶段维护。

## 固定约束

- 仅处理 `TDT/子任务＝子任务` 的记录。
- 每次运行都通过 `--base-url` 接收目标 Base URL；禁止把真实 URL、token 或 table ID 写入 Skill、项目文件或日志。
- 始终使用 user 身份和本机 lark-cli 登录态；权限不足时停止，不自动改用 bot。
- 「阶段查找」为空时，把对应快照写为 `null`，不得保留旧阶段；结果中汇总空值数量并提醒用户补充源数据。
- 「阶段查找」出现多值、未知值，或目标快照单选缺少对应选项时，列出全部异常并停止，不做部分写入。
- 同一自然周已有任意快照日期时默认停止。不要在「阶段查找」导入完成后覆盖本周快照。
- 正式写入后必须回读全部子任务，核对阶段值与本周快照日期；验证失败时报告不一致记录，不得自动重写。

## 执行流程

### 1．运行预检

先运行默认预检；它只读 Base，不写数据：

```powershell
D:\ai-workspace\shared\scripts\python.cmd `
  .agents\skills\siyuan-refresh-tdt-stage-snapshot\scripts\refresh_stage_snapshot.py `
  --base-url '"<进展 Base URL>"'
```

向用户报告：子任务总数、将复制的非空阶段数、将清空的快照数、各阶段数量、同周快照状态和全部阻塞异常。空值只简要列出总数与前 10 个子任务名称，但必须明确提醒「阶段查找」不应为空。

### 2．正常写入

预检通过后，展示影响范围并取得用户对本次写入的明确确认。使用固定确认短语：

```text
写入本周阶段快照
```

然后执行：

```powershell
D:\ai-workspace\shared\scripts\python.cmd `
  .agents\skills\siyuan-refresh-tdt-stage-snapshot\scripts\refresh_stage_snapshot.py `
  --base-url '"<进展 Base URL>"' `
  --execute `
  --confirm "写入本周阶段快照"
```

只有脚本输出“写入与回读验证通过”才算完成。

### 3．处理同周重复或未完成写入

如果本周全部记录已有快照日期，视为已经完成，停止执行。

如果只有部分记录带本周日期，视为上次写入或验证未完成。先确认外部数据源尚未刷新「阶段查找」。只有用户提供覆盖原因并明确确认该事实时，才使用：

```powershell
D:\ai-workspace\shared\scripts\python.cmd `
  .agents\skills\siyuan-refresh-tdt-stage-snapshot\scripts\refresh_stage_snapshot.py `
  --base-url '"<进展 Base URL>"' `
  --execute `
  --force-replace-this-week `
  --reason "<再次执行原因>" `
  --confirm "我确认阶段查找尚未刷新，重新覆盖本周阶段快照"
```

如果「阶段查找」已经导入或无法确认，禁止覆盖；保留现场并让用户人工判断。

## 结果汇报

正式执行后只报告：

- 快照时间与覆盖原因（如有）。
- 目标、成功验证、非空复制和空值清空的数量。
- 空值提醒及简短样例。
- 全部异常或回读不一致记录。

不要输出 Base token、完整请求体或全量正常子任务名称。
