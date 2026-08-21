#!/usr/bin/env python3
"""Safely copy TDT child-task stage lookup values into the weekly snapshot fields."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


RECORD_TYPE_FIELD = "TDT/子任务"
CHILD_RECORD_TYPE = "子任务"
TASK_NAME_FIELD = "TDT/子任务名称"
SOURCE_STAGE_FIELD = "阶段查找"
SNAPSHOT_STAGE_FIELD = "上周阶段快照（自动维护）"
SNAPSHOT_DATE_FIELD = "阶段快照日期"

NORMAL_CONFIRMATION = "写入本周阶段快照"
FORCE_CONFIRMATION = "我确认阶段查找尚未刷新，重新覆盖本周阶段快照"
TIMEZONE = dt.timezone(dt.timedelta(hours=8), name="Asia/Singapore")
PAGE_SIZE = 200
API_BATCH_SIZE = 1000
BLANK_SAMPLE_LIMIT = 10


class SnapshotError(RuntimeError):
    """Expected validation, API, or safety failure."""


@dataclass(frozen=True)
class FieldSpec:
    id: str
    name: str
    type: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequiredFields:
    record_type: FieldSpec
    task_name: FieldSpec
    source_stage: FieldSpec
    snapshot_stage: FieldSpec
    snapshot_date: FieldSpec
    child_option_id: str


@dataclass(frozen=True)
class StageRecord:
    record_id: str
    task_name: str
    source_stage: str | None
    source_values: tuple[str, ...]
    snapshot_stage: str | None
    snapshot_date: dt.datetime | None


@dataclass(frozen=True)
class SnapshotPlan:
    records: tuple[StageRecord, ...]
    snapshot_at: dt.datetime
    current_week_count: int
    blank_records: tuple[StageRecord, ...]
    stage_counts: Counter[str]

    @property
    def nonblank_count(self) -> int:
        return len(self.records) - len(self.blank_records)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="预检或刷新 TDT 子任务周度阶段快照；默认只读预检。"
    )
    parser.add_argument("--base-url", required=True, help="目标 Base URL，必须包含 table 参数")
    parser.add_argument("--lark-cli", default="lark-cli", help="lark-cli 可执行文件或命令名")
    parser.add_argument(
        "--as", dest="as_identity", default="user", choices=["user"], help="固定使用 user 身份"
    )
    parser.add_argument("--execute", action="store_true", help="通过预检后执行正式批量写入")
    parser.add_argument("--confirm", default="", help="正式写入所需的精确确认短语")
    parser.add_argument(
        "--force-replace-this-week",
        action="store_true",
        help="同周重复或部分写入时允许覆盖；仅限阶段查找尚未刷新",
    )
    parser.add_argument("--reason", default="", help="同周覆盖的具体原因")
    return parser.parse_args(argv)


def resolve_cli(value: str) -> str:
    candidate = Path(value)
    if candidate.exists():
        return str(candidate)
    found = shutil.which(value)
    if not found and os.name == "nt" and not value.lower().endswith(".cmd"):
        found = shutil.which(value + ".cmd")
    if not found:
        raise SnapshotError(f"找不到 lark-cli：{value}")
    return found


def redact(text: str, secrets: Iterable[str]) -> str:
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")
    return result


def run_lark_json(
    command: list[str],
    *,
    stdin_json: dict[str, Any] | None = None,
    secrets: Iterable[str] = (),
) -> dict[str, Any]:
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    input_text = None
    if stdin_json is not None:
        input_text = json.dumps(stdin_json, ensure_ascii=False, separators=(",", ":"))
    try:
        proc = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as error:
        raise SnapshotError(f"无法启动 lark-cli：{error}") from error
    raw = proc.stdout.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        detail = redact((proc.stderr or raw or "无输出").strip(), secrets)
        raise SnapshotError(f"lark-cli 返回了非 JSON 内容：{detail}") from error
    if not isinstance(payload, dict):
        raise SnapshotError("lark-cli 返回的 JSON 顶层不是对象")
    if payload.get("ok") is False:
        error = payload.get("error")
        detail = json.dumps(error, ensure_ascii=False) if isinstance(error, dict) else str(error)
        raise SnapshotError(f"lark-cli 调用失败：{redact(detail, secrets)}")
    if payload.get("ok") is not True and payload.get("code") not in (0, None):
        raise SnapshotError(
            f"飞书 API 调用失败：{redact(json.dumps(payload, ensure_ascii=False), secrets)}"
        )
    if proc.returncode != 0 and payload.get("ok") is not True:
        detail = redact((proc.stderr or raw).strip(), secrets)
        raise SnapshotError(f"lark-cli 退出码 {proc.returncode}：{detail}")
    return payload


def unwrap_api_data(payload: dict[str, Any]) -> dict[str, Any]:
    outer = payload.get("data", payload)
    if not isinstance(outer, dict):
        raise SnapshotError("飞书 API 返回缺少 data 对象")
    if "code" in outer:
        if outer.get("code") != 0:
            raise SnapshotError(
                f"飞书 API 错误 {outer.get('code')}：{outer.get('msg') or '未知错误'}"
            )
        inner = outer.get("data")
        if not isinstance(inner, dict):
            raise SnapshotError("飞书 API 成功响应缺少 data 对象")
        return inner
    return outer


def resolve_base(cli: str, base_url: str, identity: str) -> tuple[str, str]:
    payload = run_lark_json(
        [
            cli,
            "base",
            "+url-resolve",
            "--url",
            base_url,
            "--as",
            identity,
            "--format",
            "json",
        ],
        secrets=(base_url,),
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SnapshotError("无法从 Base URL 解析结果取得 data")
    base_token = str(data.get("base_token") or "").strip()
    table_id = str(data.get("table_id") or "").strip()
    if not base_token or not table_id:
        raise SnapshotError("Base URL 必须解析出 base_token 和 table_id")
    return base_token, table_id


def list_fields(cli: str, identity: str, base_token: str, table_id: str) -> list[FieldSpec]:
    payload = run_lark_json(
        [
            cli,
            "base",
            "+field-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            identity,
            "--limit",
            "200",
            "--offset",
            "0",
            "--format",
            "json",
        ],
        secrets=(base_token,),
    )
    data = payload.get("data")
    items = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SnapshotError("field-list 返回缺少 fields 数组")
    fields: list[FieldSpec] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        options = tuple(
            str(option.get("name"))
            for option in item.get("options", [])
            if isinstance(option, dict) and option.get("name")
        )
        fields.append(
            FieldSpec(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                type=str(item.get("type") or ""),
                options=options,
            )
        )
    return fields


def raw_field_items(
    cli: str, identity: str, base_token: str, table_id: str
) -> list[dict[str, Any]]:
    path = (
        f"/open-apis/bitable/v1/apps/{quote(base_token, safe='')}/tables/"
        f"{quote(table_id, safe='')}/fields"
    )
    page_token = ""
    items: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        payload = run_lark_json(
            [
                cli,
                "api",
                "GET",
                path,
                "--as",
                identity,
                "--params",
                json.dumps(params, separators=(",", ":")),
                "--format",
                "json",
            ],
            secrets=(base_token,),
        )
        data = unwrap_api_data(payload)
        page_items = data.get("items")
        if not isinstance(page_items, list):
            raise SnapshotError("字段 API 返回缺少 items 数组")
        items.extend(item for item in page_items if isinstance(item, dict))
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "")
        if not page_token:
            raise SnapshotError("字段 API 表示还有下一页，但未返回 page_token")
    return items


def one_field(fields: list[FieldSpec], name: str, expected_type: str) -> FieldSpec:
    matches = [field for field in fields if field.name == name]
    if len(matches) != 1:
        raise SnapshotError(f"字段「{name}」数量异常：期望 1 个，实际 {len(matches)} 个")
    field = matches[0]
    if field.type != expected_type:
        raise SnapshotError(f"字段「{name}」类型应为 {expected_type}，实际为 {field.type}")
    if not field.id:
        raise SnapshotError(f"字段「{name}」缺少 field_id")
    return field


def resolve_required_fields(
    fields: list[FieldSpec], raw_items: list[dict[str, Any]]
) -> RequiredFields:
    record_type = one_field(fields, RECORD_TYPE_FIELD, "select")
    task_name = one_field(fields, TASK_NAME_FIELD, "text")
    source_stage = one_field(fields, SOURCE_STAGE_FIELD, "lookup")
    snapshot_stage = one_field(fields, SNAPSHOT_STAGE_FIELD, "select")
    snapshot_date = one_field(fields, SNAPSHOT_DATE_FIELD, "datetime")
    if CHILD_RECORD_TYPE not in record_type.options:
        raise SnapshotError(f"字段「{RECORD_TYPE_FIELD}」缺少选项「{CHILD_RECORD_TYPE}」")
    raw_match = next(
        (
            item
            for item in raw_items
            if str(item.get("field_id") or item.get("id") or "") == record_type.id
        ),
        None,
    )
    property_data = raw_match.get("property") if isinstance(raw_match, dict) else None
    options = property_data.get("options") if isinstance(property_data, dict) else None
    option_matches = [
        option
        for option in options or []
        if isinstance(option, dict) and option.get("name") == CHILD_RECORD_TYPE
    ]
    if len(option_matches) != 1 or not option_matches[0].get("id"):
        raise SnapshotError(f"无法取得「{RECORD_TYPE_FIELD}＝{CHILD_RECORD_TYPE}」的选项 ID")
    return RequiredFields(
        record_type=record_type,
        task_name=task_name,
        source_stage=source_stage,
        snapshot_stage=snapshot_stage,
        snapshot_date=snapshot_date,
        child_option_id=str(option_matches[0]["id"]),
    )


def flatten_cell(value: Any) -> tuple[str, ...]:
    values: list[str] = []

    def visit(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            text = item.strip()
            if text:
                values.append(text)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if isinstance(item, dict):
            for key in ("name", "text", "value"):
                if key in item:
                    visit(item[key])
                    return
            values.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            return
        values.append(str(item).strip())

    visit(value)
    return tuple(dict.fromkeys(text for text in values if text))


def parse_datetime(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if abs(float(value)) >= 10_000_000_000 else float(value)
        return dt.datetime.fromtimestamp(seconds, TIMEZONE)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise SnapshotError(f"无法解析阶段快照日期：{text}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed.astimezone(TIMEZONE)


def fetch_child_records(
    cli: str,
    identity: str,
    base_token: str,
    table_id: str,
    required: RequiredFields,
) -> list[StageRecord]:
    filter_json = json.dumps(
        {
            "logic": "and",
            "conditions": [[required.record_type.id, "==", [required.child_option_id]]],
        },
        separators=(",", ":"),
    )
    projected_ids = [
        required.task_name.id,
        required.source_stage.id,
        required.snapshot_stage.id,
        required.snapshot_date.id,
    ]
    records: list[StageRecord] = []
    offset = 0
    while True:
        command = [
            cli,
            "base",
            "+record-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            identity,
            "--filter-json",
            filter_json,
        ]
        for field_id in projected_ids:
            command.extend(["--field-id", field_id])
        command.extend(
            ["--offset", str(offset), "--limit", str(PAGE_SIZE), "--format", "json"]
        )
        payload = run_lark_json(command, secrets=(base_token,))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise SnapshotError("record-list 返回缺少 data 对象")
        rows = data.get("data")
        record_ids = data.get("record_id_list")
        field_ids = data.get("field_id_list")
        if (
            not isinstance(rows, list)
            or not isinstance(record_ids, list)
            or not isinstance(field_ids, list)
        ):
            raise SnapshotError("record-list 返回缺少行、record_id 或 field_id 列表")
        indexes = {str(field_id): index for index, field_id in enumerate(field_ids)}
        missing = [field_id for field_id in projected_ids if field_id not in indexes]
        if missing:
            raise SnapshotError("record-list 未返回全部必需字段：" + "、".join(missing))
        if len(record_ids) != len(rows):
            raise SnapshotError("record-list 的记录 ID 数量与行数不一致")
        for record_id, row in zip(record_ids, rows):
            if not isinstance(row, list):
                raise SnapshotError(f"记录 {record_id} 的行数据不是数组")

            def cell(field_id: str) -> Any:
                index = indexes[field_id]
                return row[index] if index < len(row) else None

            source_values = flatten_cell(cell(required.source_stage.id))
            snapshot_values = flatten_cell(cell(required.snapshot_stage.id))
            name_values = flatten_cell(cell(required.task_name.id))
            records.append(
                StageRecord(
                    record_id=str(record_id),
                    task_name=name_values[0] if name_values else f"<未命名：{record_id}>",
                    source_stage=source_values[0] if len(source_values) == 1 else None,
                    source_values=source_values,
                    snapshot_stage=snapshot_values[0] if len(snapshot_values) == 1 else None,
                    snapshot_date=parse_datetime(cell(required.snapshot_date.id)),
                )
            )
        if not data.get("has_more") or not rows:
            break
        offset += len(rows)
        time.sleep(0.2)
    return records


def same_iso_week(value: dt.datetime, reference: dt.datetime) -> bool:
    return (
        value.astimezone(TIMEZONE).date().isocalendar()[:2]
        == reference.date().isocalendar()[:2]
    )


def build_plan(
    records: list[StageRecord],
    snapshot_options: Iterable[str],
    snapshot_at: dt.datetime,
) -> SnapshotPlan:
    if not records:
        raise SnapshotError("未找到任何 TDT 子任务，停止执行")
    allowed = set(snapshot_options)
    anomalies: list[str] = []
    for record in records:
        if len(record.source_values) > 1:
            anomalies.append(
                f"{record.task_name}（{record.record_id}）：阶段查找为多值 {list(record.source_values)}"
            )
        elif record.source_stage and record.source_stage not in allowed:
            anomalies.append(
                f"{record.task_name}（{record.record_id}）：阶段查找值「{record.source_stage}」不在快照单选项中"
            )
    if anomalies:
        raise SnapshotError("数据异常，未写入：\n" + "\n".join(f"- {item}" for item in anomalies))
    current_week_count = sum(
        1
        for record in records
        if record.snapshot_date and same_iso_week(record.snapshot_date, snapshot_at)
    )
    blank_records = tuple(record for record in records if record.source_stage is None)
    stage_counts: Counter[str] = Counter(
        record.source_stage for record in records if record.source_stage is not None
    )
    return SnapshotPlan(
        records=tuple(records),
        snapshot_at=snapshot_at,
        current_week_count=current_week_count,
        blank_records=blank_records,
        stage_counts=stage_counts,
    )


def validate_execution_gate(args: argparse.Namespace, plan: SnapshotPlan) -> None:
    if not args.execute:
        return
    if plan.current_week_count:
        if not args.force_replace_this_week:
            state = "全部" if plan.current_week_count == len(plan.records) else "部分"
            raise SnapshotError(
                f"本周已有{state}快照日期（{plan.current_week_count}/{len(plan.records)}），默认禁止重复执行。"
                "若确认阶段查找尚未刷新，请提供覆盖原因、--force-replace-this-week 和专用确认短语。"
            )
        if not args.reason.strip():
            raise SnapshotError("同周覆盖必须通过 --reason 提供具体原因")
        if args.confirm != FORCE_CONFIRMATION:
            raise SnapshotError(f"同周覆盖确认短语不匹配；必须精确输入：{FORCE_CONFIRMATION}")
    else:
        if args.force_replace_this_week:
            raise SnapshotError("本周没有既有快照，不需要 --force-replace-this-week")
        if args.confirm != NORMAL_CONFIRMATION:
            raise SnapshotError(f"正式写入确认短语不匹配；必须精确输入：{NORMAL_CONFIRMATION}")


def snapshot_epoch_ms(snapshot_at: dt.datetime) -> int:
    return int(snapshot_at.timestamp() * 1000)


def build_update_records(
    plan: SnapshotPlan, required: RequiredFields
) -> list[dict[str, Any]]:
    timestamp = snapshot_epoch_ms(plan.snapshot_at)
    return [
        {
            "record_id": record.record_id,
            "fields": {
                required.snapshot_stage.name: record.source_stage,
                required.snapshot_date.name: timestamp,
            },
        }
        for record in plan.records
    ]


def batch_update(
    cli: str,
    identity: str,
    base_token: str,
    table_id: str,
    updates: list[dict[str, Any]],
) -> None:
    path = (
        f"/open-apis/bitable/v1/apps/{quote(base_token, safe='')}/tables/"
        f"{quote(table_id, safe='')}/records/batch_update"
    )
    for start in range(0, len(updates), API_BATCH_SIZE):
        chunk = updates[start : start + API_BATCH_SIZE]
        payload = run_lark_json(
            [
                cli,
                "api",
                "POST",
                path,
                "--as",
                identity,
                "--data",
                "-",
                "--format",
                "json",
            ],
            stdin_json={"records": chunk},
            secrets=(base_token,),
        )
        data = unwrap_api_data(payload)
        returned = data.get("records")
        if not isinstance(returned, list) or len(returned) != len(chunk):
            actual = len(returned) if isinstance(returned, list) else "未知"
            raise SnapshotError(f"批量写入返回数量异常：请求 {len(chunk)}，返回 {actual}")
        if start + len(chunk) < len(updates):
            time.sleep(1.0)


def verification_errors(before: SnapshotPlan, after: list[StageRecord]) -> list[str]:
    after_by_id = {record.record_id: record for record in after}
    errors: list[str] = []
    for expected in before.records:
        actual = after_by_id.get(expected.record_id)
        if not actual:
            errors.append(f"{expected.task_name}（{expected.record_id}）：回读时记录缺失")
            continue
        if actual.source_values != expected.source_values:
            errors.append(
                f"{expected.task_name}（{expected.record_id}）：写入期间阶段查找发生变化，"
                f"预检值 {list(expected.source_values)}，回读值 {list(actual.source_values)}"
            )
        if actual.snapshot_stage != expected.source_stage:
            errors.append(
                f"{expected.task_name}（{expected.record_id}）：快照期望「{expected.source_stage or '空'}」，"
                f"实际「{actual.snapshot_stage or '空'}」"
            )
        if not actual.snapshot_date:
            errors.append(f"{expected.task_name}（{expected.record_id}）：阶段快照日期为空")
        elif int(actual.snapshot_date.timestamp()) != int(before.snapshot_at.timestamp()):
            errors.append(
                f"{expected.task_name}（{expected.record_id}）：阶段快照日期不是本次执行时间"
            )
    extra = set(after_by_id) - {record.record_id for record in before.records}
    if extra:
        errors.append("回读出现预检范围外记录：" + "、".join(sorted(extra)))
    return errors


def print_plan(plan: SnapshotPlan, *, execute: bool, reason: str = "") -> None:
    iso_year, iso_week, _ = plan.snapshot_at.date().isocalendar()
    mode = "正式执行" if execute else "只读预检"
    print(f"模式：{mode}")
    print(f"计划快照时间：{plan.snapshot_at:%Y-%m-%d %H:%M:%S}")
    print(f"快照周次：{iso_year} · W{iso_week:02d}")
    print(f"目标子任务：{len(plan.records)}")
    print(f"复制非空阶段：{plan.nonblank_count}")
    print(f"清空旧快照：{len(plan.blank_records)}")
    print(f"本周已有快照日期：{plan.current_week_count}")
    if reason:
        print(f"同周覆盖原因：{reason}")
    if plan.stage_counts:
        summary = "、".join(
            f"{stage} {count}" for stage, count in sorted(plan.stage_counts.items())
        )
        print(f"阶段分布：{summary}")
    if plan.blank_records:
        samples = "、".join(
            record.task_name for record in plan.blank_records[:BLANK_SAMPLE_LIMIT]
        )
        suffix = "……" if len(plan.blank_records) > BLANK_SAMPLE_LIMIT else ""
        print(
            f"警告：发现 {len(plan.blank_records)} 条「阶段查找」为空；执行时会同步清空快照。"
            "阶段查找按业务规则不应为空，请在刷新后补充源数据。"
        )
        print(f"空值样例：{samples}{suffix}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot_at = dt.datetime.now(TIMEZONE).replace(microsecond=0)
    base_token = ""
    try:
        cli = resolve_cli(args.lark_cli)
        base_token, table_id = resolve_base(cli, args.base_url, args.as_identity)
        fields = list_fields(cli, args.as_identity, base_token, table_id)
        raw_items = raw_field_items(cli, args.as_identity, base_token, table_id)
        required = resolve_required_fields(fields, raw_items)
        records = fetch_child_records(cli, args.as_identity, base_token, table_id, required)
        plan = build_plan(records, required.snapshot_stage.options, snapshot_at)
        print_plan(plan, execute=args.execute, reason=args.reason.strip())
        validate_execution_gate(args, plan)
        if not args.execute:
            if plan.current_week_count:
                state = (
                    "已全部完成"
                    if plan.current_week_count == len(plan.records)
                    else "存在部分写入"
                )
                print(f"预检结论：本周快照{state}，正式执行将被重复保护拦截。")
            else:
                print(f"预检结论：通过。正式写入需确认短语「{NORMAL_CONFIRMATION}」。")
            return 0
        updates = build_update_records(plan, required)
        batch_update(cli, args.as_identity, base_token, table_id, updates)
        time.sleep(1.0)
        after = fetch_child_records(cli, args.as_identity, base_token, table_id, required)
        errors = verification_errors(plan, after)
        if errors:
            raise SnapshotError(
                "写入已发出，但回读验证失败；禁止自动重写：\n"
                + "\n".join(f"- {item}" for item in errors)
            )
        print(f"写入与回读验证通过：{len(plan.records)}/{len(plan.records)} 条子任务。")
        return 0
    except SnapshotError as error:
        message = redact(str(error), (args.base_url, base_token))
        print(f"错误：{message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
