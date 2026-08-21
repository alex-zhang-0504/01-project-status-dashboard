#!/usr/bin/env python3
"""Generate the TDT weekly-meeting dashboard HTML from Feishu/Lark Base data.

Data-access, field-tolerance, and progress-parsing functions are copied from
skills-dev/siyuan-baseinfo-to-weeklyreport/scripts/generate_weekly_report.py
(marked "copied from weeklyreport") so the original skill stays untouched.

Flow: read the locked view and the whole table, classify every record only by
the ``TDT/子任务`` field (``TDT`` = parent, ``子任务`` = child), then use the
``父记录`` link only to associate a child with its parent TDT. Compute
render-ready data (grouping, milestone states, control points, progress
split), inject JSON into the selected template, and write a self-contained
HTML into output/.

Runtime Base-mapping contract: within records selected for the dashboard and
fields explicitly mapped below, only ``None``, an empty string, or whitespace
is blank. Every other Base value remains visibly represented. Formatting and
documented normalization are allowed; record filters, date-range selection,
latest-block extraction, field fallback, and aggregation remain explicit
business-scope rules and must not be changed implicitly by value rendering.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

EXPECTED_VIEW_NAME = "TDT技术项目总表"
RECORD_TYPE_FIELD = "TDT/子任务"
TDT_RECORD_TYPE = "TDT"
CHILD_RECORD_TYPE = "子任务"
PRODUCT_GENERATION_FIELD = "4+4+1 @26"
VALUE_DECISION_FIELD = "价值决策"
STAGE_FIELD = "阶段查找"
CONTROL_POINT_FIELD = "阶段控制点"
PROJECT_STATUS_FIELD = "状态查找"
STAGE_COMPARISON_FIELD = "阶段对比结果"
RISK_STATUS_FIELD = "风险状态"

IN_DEVELOPMENT_PROJECT_STATUS = "进行中"
COMPLETED_PROJECT_STATUSES = (
    "已完成",
    "开发完成_正常",
    "开发完成_顺延",
    "开发完成_变更",
    "开发完成_风险",
    "开发完成_技术不可行",
    "开发完成_价值fail",
    "开发完成_进度fail",
)
PAUSED_PROJECT_STATUSES = {"暂停"}
CANCELED_PROJECT_STATUSES = {"取消", "已取消"}
REJECTED_PROJECT_STATUSES = {"驳回"}

REQUIRED_FIELDS = [
    "TDT/子任务名称",
    RECORD_TYPE_FIELD,
    "赛道",
    PRODUCT_GENERATION_FIELD,
    "父记录",
    "项目编码",
    VALUE_DECISION_FIELD,
    "TDR1计划",
    "TDR1实际",
    "TDR2(KO)",
    "TDR2实际",
    "TDR3预计",
    "TDR3实际",
    RISK_STATUS_FIELD,
    STAGE_FIELD,
    CONTROL_POINT_FIELD,
    PROJECT_STATUS_FIELD,
    STAGE_COMPARISON_FIELD,
    "最新进展描述",
    "项目风险",
    "TDT PM",
    "子任务 PM",
    "最近更新时间",
]

OVERVIEW_TRACK_TEXT_COUNT = 13
TIME_ZONE = dt.timezone(dt.timedelta(hours=8), name="Asia/Shanghai")

ISSUE_FIELDS = [
    "Item",
    "TDT项目子任务名称",
    "任务",
    "当前进展",
    "计划完成日期",
    "调整日期",
    "实际完成日期",
    "提出人",
    "责任部门",
    "责任人",
    "任务状态",
    "Week",
]
ISSUE_DISPLAY_FIELDS = [field for field in ISSUE_FIELDS if field != "Week"]

INNOVATION_FIELDS = (
    "项目名称",
    "技术赛道",
    "项目阶段",
    "项目状态",
    "项目风险",
)
INNOVATION_ORDER_FIELD = "No."
INNOVATION_IN_PROGRESS_STATUS = "进行中"
INNOVATION_COMPLETED_STATUS = "已完成"
INNOVATION_CANCELED_STATUS = "已取消"

RISK_ORDER = {"高风险": 0, "中风险": 1, "低风险": 2, "/": 3}

# copied from weeklyreport
LEADING_UPDATE_DATE_RE = re.compile(
    r"^\s*(?P<date>"
    r"(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})"
    r"|(?:\d{1,2}[-/.]\d{1,2})"
    r"|(?:\d{1,2}月\d{1,2}日)"
    r")\s*(?:[:：、，,\-\s]|$)"
)
# copied from weeklyreport，并增加同一行以分号分隔旧日期段的容错：
# 仅"行首或分号后的合法日期 + 中/英文冒号"才算新的一段更新。
PROGRESS_DATE_BLOCK_RE = re.compile(
    r"(?m)(?:^|[;；])[ \t　]*(?P<date>"
    r"(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})"
    r"|(?:\d{1,2}[-/.]\d{1,2})"
    r"|(?:\d{3,4})"
    r"|(?:\d{1,2}月\d{1,2}日)"
    r")[ \t　]*[:：]"
)
CURRENT_LABEL_RE = re.compile(r"(本周进展|本周计划|本周状态|本周进度|本周完成|本周工作|本周事项|本周)\s*[:：]")
NEXT_LABEL_RE = re.compile(r"(下周计划|下周进展|下周安排|下步计划|后续计划|下周)\s*[:：]")
TIME_SUFFIX_RE = re.compile(r"\s+00:00:00$")
BASE_DATE_TZ = dt.timezone(dt.timedelta(hours=8))
NUMBERED_ITEM_MARKER = r"(?:\d+、|\d+\.(?!\d)|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])"
NUMBERED_ITEM_RE = re.compile(rf"(?=(?:^|\n)\s*{NUMBERED_ITEM_MARKER})")
VISUAL_MODEL_DIMENSION = r"(?:2(?:\.5)?D|3D|4D)"
COMPACT_VISUAL_MODEL_NUMBERED_ITEM_RE = re.compile(
    rf"(?m)(?P<prefix>^|[;；\r\n])(?P<number>\d+)\.(?P<dimension>{VISUAL_MODEL_DIMENSION})"
)


class SkillError(RuntimeError):
    pass


def log(logs: list[str], message: str) -> None:
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}"
    logs.append(line)
    print(line)


def redact_secret(value: Any, secret: str) -> str:
    """CLI 错误可读化，同时避免把 Base token 写入终端或报告。"""
    text = str(value or "")
    return text.replace(secret, "<base-token>") if secret else text


def lark_error_message(payload: dict[str, Any], base_token: str) -> str:
    error = payload.get("error")
    message = error.get("message") if isinstance(error, dict) else error
    return redact_secret(message or payload, base_token)


# copied from weeklyreport
def parse_base_link(link: str) -> tuple[str, str | None, str | None]:
    parsed = urlparse(link)
    match = re.search(r"/base/([^/?#]+)", parsed.path)
    if not match:
        raise SkillError("无法从 Base 链接解析 base-token，请检查链接格式")
    query = parse_qs(parsed.query)
    table_id = query.get("table", [None])[0]
    view_id = query.get("view", [None])[0]
    return match.group(1), table_id, view_id


# copied from weeklyreport
def normalize_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and "name" in item:
                parts.append(str(item["name"]))
            elif item is not None:
                parts.append(str(item))
        return "、".join(parts)
    if isinstance(value, dict) and "name" in value:
        return str(value["name"])
    return str(value)


# copied from weeklyreport
def normalize_match_key(value: str) -> str:
    value = (value or "").casefold()
    return "".join(ch for ch in value if ch.isalnum() or "一" <= ch <= "鿿")


def is_tdt_record(record: dict[str, str]) -> bool:
    """记录层级唯一依据：TDT/子任务＝TDT。"""
    return normalize_match_key(record.get(RECORD_TYPE_FIELD, "")) == normalize_match_key(TDT_RECORD_TYPE)


def is_child_task_record(record: dict[str, str]) -> bool:
    """记录层级唯一依据：TDT/子任务＝子任务。"""
    return normalize_match_key(record.get(RECORD_TYPE_FIELD, "")) == normalize_match_key(CHILD_RECORD_TYPE)


def accepted_filter_values(filter_value: str) -> set[str]:
    """兼容「是/否」单选与 True/False 勾选框，但不混淆正反值。"""
    expected = normalize_match_key(filter_value)
    accepted = {expected}
    if expected in {normalize_match_key("是"), "true"}:
        accepted.add("true")
    elif expected in {normalize_match_key("否"), "false"}:
        accepted.add("false")
    return accepted


def split_option_values(raw: str) -> set[str]:
    """把 select／lookup 的规范化文本拆成非空选项集合。"""
    return {value.strip() for value in (raw or "").split("、") if value.strip()}


def extract_field_option_orders(
    field_payload: dict[str, Any],
    field_names: tuple[str, ...],
) -> dict[str, list[str]]:
    """从 Base 字段元数据读取选项顺序，未知字段返回空顺序。"""
    orders = {name: [] for name in field_names}
    fields = field_payload.get("data", {}).get("fields", [])
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "")).strip()
        if name not in orders:
            continue
        options = field.get("options")
        if not isinstance(options, list):
            continue
        orders[name] = [
            str(option.get("name", "")).strip()
            for option in options
            if isinstance(option, dict) and str(option.get("name", "")).strip()
        ]
    return orders


def normalize_product_generation_brand(value: str) -> str:
    """产品代选项按已确认的品牌前缀归一，其他值保持 Base 原名。"""
    value = (value or "").strip()
    upper_value = value.upper()
    for brand in ("GT", "NOTE", "CAMON", "POVA"):
        if upper_value.startswith(brand):
            return brand
    return value


def aggregate_field_categories(
    records: list[dict[str, str]],
    field_name: str,
    option_order: list[str] | None = None,
    category_normalizer: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """按字段实际非空选项计数，并优先沿用 Base 字段选项顺序。"""
    normalize_category = category_normalizer or (lambda value: value)
    counts: dict[str, int] = {}
    first_seen: list[str] = []
    for record in records:
        categories = []
        for raw_value in (record.get(field_name, "") or "").split("、"):
            value = normalize_category(raw_value.strip())
            if value and value not in categories:
                categories.append(value)
        for value in categories:
            if value not in counts:
                counts[value] = 0
                first_seen.append(value)
            counts[value] += 1

    normalized_option_order = []
    for value in option_order or []:
        normalized_value = normalize_category(value)
        if normalized_value and normalized_value not in normalized_option_order:
            normalized_option_order.append(normalized_value)
    ordered_values = [value for value in normalized_option_order if value in counts]
    ordered_values.extend(value for value in first_seen if value not in ordered_values)
    return [
        {"key": value, "name": value, "label": value, "count": counts[value]}
        for value in ordered_values
    ]


# copied from weeklyreport
def strip_field_suffix(name: str) -> str:
    return re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", (name or "").strip())


# copied from weeklyreport（REQUIRED_FIELDS 换成本脚本清单）
def resolve_field_names(actual_fields: list[str]) -> dict[str, str]:
    actual_set = set(actual_fields)
    tolerant_index: dict[str, str] = {}
    for actual in actual_fields:
        tolerant_index.setdefault(normalize_match_key(strip_field_suffix(actual)), actual)
    resolved: dict[str, str] = {}
    for canonical in REQUIRED_FIELDS:
        if canonical in actual_set:
            resolved[canonical] = canonical
            continue
        actual = tolerant_index.get(normalize_match_key(canonical))
        if actual:
            resolved[canonical] = actual
    return resolved


# copied from weeklyreport
def extract_link_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
    return result


# copied from weeklyreport
def parse_epoch_date(value: str) -> dt.date | None:
    match = re.fullmatch(r"(\d{13}|\d{10})(?:\.0+)?", value)
    if not match:
        return None
    digits = match.group(1)
    seconds = int(digits) / 1000 if len(digits) == 13 else int(digits)
    try:
        parsed = dt.datetime.fromtimestamp(seconds, tz=BASE_DATE_TZ)
    except (OverflowError, OSError, ValueError):
        return None
    if not 2000 <= parsed.year <= 2099:
        return None
    return parsed.date()


def parse_base_date(value: str) -> dt.date | None:
    """Base 单元格值 -> date；兼容 '2026-06-29 00:00:00'、'2026/06/29'、epoch 毫秒/秒。"""
    value = (value or "").strip()
    if not value or value == "/":
        return None
    value = TIME_SUFFIX_RE.sub("", value)
    epoch = parse_epoch_date(value)
    if epoch is not None:
        return epoch
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if match:
        try:
            return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


# copied from weeklyreport
def infer_date(raw: str, run_date: dt.date) -> dt.date | None:
    raw = raw.strip()
    try:
        year_inferred = False
        if "月" in raw:
            month, day = map(int, re.findall(r"\d+", raw)[:2])
            year = run_date.year
            year_inferred = True
        else:
            nums = list(map(int, re.findall(r"\d+", raw)))
            if len(nums) == 3:
                year, month, day = nums
            elif len(nums) == 2:
                year = run_date.year
                month, day = nums
                year_inferred = True
            elif len(nums) == 1 and re.fullmatch(r"\d{3,4}", raw):
                year = run_date.year
                month, day = int(raw[:-2]), int(raw[-2:])
                year_inferred = True
            else:
                return None
        candidate = dt.date(year, month, day)
        if year_inferred and candidate > run_date + dt.timedelta(days=7):
            candidate = dt.date(year - 1, month, day)
        return candidate
    except ValueError:
        return None


# copied from weeklyreport
def strip_leading_progress_date(text: str, warnings: list[str], task_name: str) -> str:
    text = (text or "").strip()
    if not text:
        warnings.append(f"子任务'{task_name}'的最新进展描述为空")
        return ""
    match = LEADING_UPDATE_DATE_RE.match(text)
    if not match:
        warnings.append(f"子任务'{task_name}'的最新进展描述开头未识别到更新日期，已按全文解析")
        return text
    return text[match.end():].strip(" \t\r\n:：、，,-")


# copied from weeklyreport
def select_latest_progress_block(text: str, run_date: dt.date, warnings: list[str], task_name: str) -> str:
    text = (text or "").strip()
    if not text:
        warnings.append(f"子任务'{task_name}'的最新进展描述为空")
        return ""
    valid = [
        (match, infer_date(match.group("date"), run_date))
        for match in PROGRESS_DATE_BLOCK_RE.finditer(text)
    ]
    valid = [(match, day) for match, day in valid if day is not None]
    if not valid:
        return strip_leading_progress_date(text, warnings, task_name)
    blocks = []
    for i, (match, day) in enumerate(valid):
        end = valid[i + 1][0].start() if i + 1 < len(valid) else len(text)
        body = text[match.end():end].strip(" \t\r\n:：、，,-　")
        blocks.append((day, body))
    orphan = text[: valid[0][0].start()].strip()
    if orphan:
        warnings.append(
            f"子任务'{task_name}'最新进展描述首个日期段前存在未归类文本，已忽略：{orphan[:30]}"
        )
    max_date = max(day for _, day in valid)
    chosen = [body for day, body in blocks if day == max_date and body]
    result = "\n".join(chosen).strip()
    if not result:
        warnings.append(f"子任务'{task_name}'最新进展描述最新日期段内容为空")
    return result


# copied from weeklyreport
def format_numbered_spacing(
    text: str,
    add_blank_between_items: bool,
    *,
    compact_visual_model_numbering: bool = False,
) -> str:
    """按人工编号分行；仅进展／风险兼容「2.3D」这类紧凑写法。"""
    text = mapped_base_value(text)
    if not text:
        return ""
    if compact_visual_model_numbering:
        text = COMPACT_VISUAL_MODEL_NUMBERED_ITEM_RE.sub(
            lambda match: f"{match.group('prefix')}{match.group('number')}. {match.group('dimension')}",
            text,
        )
    normalized = re.sub(rf"(?<!\d)\s*(?={NUMBERED_ITEM_MARKER})", "\n", text).strip()
    parts = [part.strip() for part in NUMBERED_ITEM_RE.split(normalized) if part.strip()]
    if len(parts) <= 1:
        return normalized
    return ("\n\n" if add_blank_between_items else "\n").join(parts)


# copied from weeklyreport
def split_progress(text: str, run_date: dt.date, warnings: list[str], task_name: str) -> tuple[str, str]:
    block = select_latest_progress_block(text, run_date, warnings, task_name)
    if not block:
        return "", ""
    current_match = CURRENT_LABEL_RE.search(block)
    next_match = NEXT_LABEL_RE.search(block)
    if current_match and next_match and current_match.start() < next_match.start():
        current = block[current_match.end(): next_match.start()].strip()
        next_plan = block[next_match.end():].strip()
    elif current_match:
        current = block[current_match.end():].strip()
        next_plan = ""
    elif next_match:
        current = block[: next_match.start()].strip()
        next_plan = block[next_match.end():].strip()
    else:
        warnings.append(f"子任务'{task_name}'的最近日期更新块未找到本周/下周标记，已将正文写入本周进展，下周计划保持为空")
        current = block.strip()
        next_plan = ""
    return (
        format_numbered_spacing(
            current,
            add_blank_between_items=False,
            compact_visual_model_numbering=True,
        ),
        format_numbered_spacing(
            next_plan,
            add_blank_between_items=False,
            compact_visual_model_numbering=True,
        ),
    )


def to_items(text: str) -> list[str]:
    """格式化后的多行文本 -> 条目数组（真正空值 -> []）。"""
    text = mapped_base_value(text)
    if not text:
        return []
    return [line.strip() for line in text.split("\n") if line.strip()]


def parse_control_points(text: str) -> list[str]:
    """阶段控制点字段 -> 保留人工序号的逐行条目。"""
    formatted = format_numbered_spacing(text, add_blank_between_items=False)
    return to_items(formatted)


# copied from weeklyreport
def run_lark_record_list(
    lark_cli: str,
    as_identity: str,
    base_token: str,
    table_id: str,
    offset: int,
    limit: int,
    view_id: str | None,
    field_ids: list[str] | None = None,
    sort_json: str | None = None,
) -> dict[str, Any]:
    cmd = [
        lark_cli, "base", "+record-list",
        "--as", as_identity,
        "--base-token", base_token,
        "--table-id", table_id,
        "--format", "json",
        "--offset", str(offset),
        "--limit", str(limit),
    ]
    if view_id:
        cmd.extend(["--view-id", view_id])
    for field_id in field_ids or []:
        cmd.extend(["--field-id", field_id])
    if sort_json:
        cmd.extend(["--sort-json", sort_json])
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = redact_secret(proc.stderr or proc.stdout, base_token)
        raise SkillError(f"lark-cli record-list 失败：{detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise SkillError("lark-cli record-list 返回了无法解析的 JSON") from error
    if not isinstance(payload, dict):
        raise SkillError("lark-cli record-list 返回的 JSON 顶层不是对象")
    if not payload.get("ok"):
        message = lark_error_message(payload, base_token)
        raise SkillError(f"读取 Base 记录失败：{message}")
    return payload


def run_lark_record_created_time_page(
    lark_cli: str,
    as_identity: str,
    base_token: str,
    table_id: str,
    primary_field_name: str,
    page_token: str | None,
) -> dict[str, Any]:
    """调用官方查询记录接口，显式返回系统创建时间。"""
    path = f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/search"
    params: dict[str, Any] = {"page_size": 500}
    if page_token:
        params["page_token"] = page_token
    body = {
        "automatic_fields": True,
        "field_names": [primary_field_name],
    }
    cmd = [
        lark_cli,
        "api",
        "POST",
        path,
        "--as",
        as_identity,
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--data",
        json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = redact_secret(proc.stderr or proc.stdout, base_token)
        raise SkillError(f"读取 Base 记录系统创建时间失败：{detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise SkillError("查询 Base 记录系统创建时间返回了无法解析的 JSON") from error
    if not isinstance(payload, dict):
        raise SkillError("查询 Base 记录系统创建时间返回的 JSON 顶层不是对象")
    if not payload.get("ok"):
        message = lark_error_message(payload, base_token)
        raise SkillError(f"读取 Base 记录系统创建时间失败：{message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SkillError("查询 Base 记录系统创建时间返回结果缺少 data")
    return data


def scan_record_created_times(
    *,
    base_token: str,
    table_id: str,
    primary_field_name: str,
    lark_cli: str,
    as_identity: str,
    page_delay: float,
    logs: list[str],
) -> dict[str, str]:
    """完整分页读取记录 ID 与系统创建时间。"""
    created_times: dict[str, str] = {}
    page_token: str | None = None
    page_number = 1
    while True:
        log(logs, f"分页读取 Base 记录系统创建时间：page={page_number}, limit=500")
        data = run_lark_record_created_time_page(
            lark_cli,
            as_identity,
            base_token,
            table_id,
            primary_field_name,
            page_token,
        )
        items = data.get("items", [])
        if not isinstance(items, list):
            raise SkillError("查询 Base 记录系统创建时间返回的 items 不是数组")
        for item in items:
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("record_id", "")).strip()
            if record_id:
                created_times[record_id] = str(item.get("created_time", "")).strip()
        if not data.get("has_more"):
            break
        next_token = str(data.get("page_token", "")).strip()
        if not next_token:
            raise SkillError("查询 Base 记录系统创建时间失败：分页响应缺少 page_token")
        page_token = next_token
        page_number += 1
        if page_delay > 0:
            time.sleep(page_delay)
    return created_times


def run_lark_field_list(
    lark_cli: str,
    as_identity: str,
    base_token: str,
    table_id: str,
) -> dict[str, Any]:
    cmd = [
        lark_cli, "base", "+field-list",
        "--as", as_identity,
        "--base-token", base_token,
        "--table-id", table_id,
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = redact_secret(proc.stderr or proc.stdout, base_token)
        raise SkillError(f"lark-cli field-list 失败：{detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise SkillError("lark-cli field-list 返回了无法解析的 JSON") from error
    if not isinstance(payload, dict):
        raise SkillError("lark-cli field-list 返回的 JSON 顶层不是对象")
    if not payload.get("ok"):
        message = lark_error_message(payload, base_token)
        raise SkillError(f"读取 Base 字段失败：{message}")
    return payload


def build_project_overview(
    *,
    records: list[dict[str, str]],
    logs: list[str],
    field_option_orders: dict[str, list[str]] | None = None,
    run_date: dt.date,
    warnings: list[str],
) -> dict[str, Any]:
    """基于已完整分页读取的记录统计子任务赛道与规划导入产品代分布。"""
    children = [record for record in records if is_child_task_record(record)]
    option_orders = field_option_orders or {}
    tracks = aggregate_field_categories(children, "赛道", option_orders.get("赛道"))
    product_generations = aggregate_field_categories(
        children,
        PRODUCT_GENERATION_FIELD,
        option_orders.get(PRODUCT_GENERATION_FIELD),
        normalize_product_generation_brand,
    )

    weekly_children: list[dict[str, str]] = []
    invalid_created_time_projects: list[dict[str, str]] = []
    run_iso_year, run_iso_week, _ = run_date.isocalendar()
    for record in children:
        raw_created_time = (record.get("_created_time", "") or "").strip()
        created_date: dt.date | None = None
        if re.fullmatch(r"\d{10}|\d{13}", raw_created_time):
            timestamp = int(raw_created_time)
            if len(raw_created_time) == 13:
                timestamp /= 1000
            try:
                created_date = dt.datetime.fromtimestamp(
                    timestamp,
                    tz=dt.timezone.utc,
                ).astimezone(TIME_ZONE).date()
            except (OverflowError, OSError, ValueError):
                created_date = None
            if created_date and not 2000 <= created_date.year <= 2099:
                created_date = None
        if created_date is None:
            invalid_created_time_projects.append({
                "code": mapped_base_value(record.get("项目编码", "")),
                "name": mapped_base_value(record.get("TDT/子任务名称", "")),
            })
            continue
        created_iso_year, created_iso_week, _ = created_date.isocalendar()
        if (created_iso_year, created_iso_week) == (run_iso_year, run_iso_week):
            weekly_children.append(record)

    weekly_tracks = aggregate_field_categories(
        weekly_children,
        "赛道",
        option_orders.get("赛道"),
    )
    missing_track_records = [
        record for record in weekly_children
        if not mapped_base_value(record.get("赛道", ""))
    ]
    missing_track_projects = [{
        "code": mapped_base_value(record.get("项目编码", "")),
        "name": mapped_base_value(record.get("TDT/子任务名称", "")),
    } for record in missing_track_records]

    def reference_text(project: dict[str, str]) -> str:
        return " ".join(value for value in (project["code"], project["name"]) if value)

    if missing_track_projects:
        references = "、".join(filter(None, map(reference_text, missing_track_projects)))
        detail = f"，涉及：{references}" if references else ""
        warnings.append(
            f"本周新增项目中有 {len(missing_track_projects)} 条未填写赛道{detail}；"
            "请补充后重新生成"
        )
    if invalid_created_time_projects:
        references = "、".join(filter(None, map(reference_text, invalid_created_time_projects)))
        detail = f"，涉及：{references}" if references else ""
        warnings.append(
            f"有 {len(invalid_created_time_projects)} 条子任务的系统创建时间缺失或无法解析，"
            f"未计入本周新增{detail}"
        )

    total = len(children)
    grouped_total = sum(item["count"] for item in tracks)
    unassigned_count = max(total - grouped_total, 0)
    generation_summary = "、".join(
        f"{item['label']} {item['count']} 个" for item in product_generations
    ) or "无有效分类"
    log(
        logs,
        f"项目概况聚合完成：子任务 {total} 个，赛道文字固定 {OVERVIEW_TRACK_TEXT_COUNT} 个，"
        f"柱状图分类 {len(tracks)} 个；规划导入 {generation_summary}",
    )
    return {
        "enabled": True,
        "total": total,
        "trackCount": OVERVIEW_TRACK_TEXT_COUNT,
        "unassignedCount": unassigned_count,
        "tracks": tracks,
        "unmappedTracks": [],
        "productGenerations": product_generations,
        "unmappedProductGenerationOptions": [],
        "weeklyAddition": {
            "total": len(weekly_children),
            "tracks": weekly_tracks,
            "missingTrackCount": len(missing_track_projects),
            "missingTrackProjects": missing_track_projects,
            "invalidCreatedTimeCount": len(invalid_created_time_projects),
            "invalidCreatedTimeProjects": invalid_created_time_projects,
        },
    }


def status_contains_keyword(value: str, keyword: str) -> bool:
    """按项目状态文本的关键词统计，忽略英文大小写。"""
    return keyword.casefold() in (value or "").casefold()


def build_development_summary(
    records: list[dict[str, str]],
    logs: list[str],
) -> dict[str, Any]:
    """从全量子任务装配开发达成统计和本周阶段变化明细。"""
    children = [record for record in records if is_child_task_record(record)]
    status_counts = {
        "inDevelopment": 0,
        "completed": 0,
        "paused": 0,
        "canceled": 0,
        "rejected": 0,
        "unclassified": 0,
    }
    completed_statuses = set(COMPLETED_PROJECT_STATUSES)
    for record in children:
        values = split_option_values(record.get(PROJECT_STATUS_FIELD, ""))
        if values & completed_statuses:
            status_counts["completed"] += 1
        elif IN_DEVELOPMENT_PROJECT_STATUS in values:
            status_counts["inDevelopment"] += 1
        elif values & PAUSED_PROJECT_STATUSES:
            status_counts["paused"] += 1
        elif values & CANCELED_PROJECT_STATUSES:
            status_counts["canceled"] += 1
        elif values & REJECTED_PROJECT_STATUSES:
            status_counts["rejected"] += 1
        else:
            status_counts["unclassified"] += 1

    risk_counts = {"medium": 0, "high": 0, "delayed": 0, "fail": 0}
    for record in children:
        risk_values = split_option_values(record.get(RISK_STATUS_FIELD, ""))
        status_values = split_option_values(record.get(PROJECT_STATUS_FIELD, ""))
        risk_counts["medium"] += int("中风险" in risk_values)
        risk_counts["high"] += int("高风险" in risk_values)
        risk_counts["delayed"] += int(any(status_contains_keyword(value, "延期") for value in status_values))
        risk_counts["fail"] += int(any(status_contains_keyword(value, "fail") for value in status_values))
    numerator = sum(risk_counts.values())
    denominator = status_counts["inDevelopment"] + status_counts["completed"]
    achievement_rate = None
    if denominator:
        achievement_rate = round((1 - numerator / denominator) * 100, 1)

    new_in_development: list[dict[str, str]] = []
    new_completed: list[dict[str, str]] = []
    for record in children:
        comparison = (record.get(STAGE_COMPARISON_FIELD, "") or "").strip()
        if comparison not in {"新增开发中", "新增已结项"}:
            continue
        item = {
            "track": mapped_base_value(record.get("赛道", "")),
            "name": mapped_base_value(record.get("TDT/子任务名称", "")),
        }
        if comparison == "新增开发中":
            new_in_development.append(item)
        else:
            new_completed.append(item)

    log(
        logs,
        "开发达成概况装配完成："
        f"子任务 {len(children)} 个，开发中 {status_counts['inDevelopment']} 个，"
        f"已结项 {status_counts['completed']} 个，新增开发中 {len(new_in_development)} 个，"
        f"新增已结项 {len(new_completed)} 个，预估达成率 "
        f"{achievement_rate if achievement_rate is not None else '不可计算'}%",
    )
    return {
        "enabled": True,
        "total": len(children),
        "achievementRate": achievement_rate,
        "statusCounts": status_counts,
        "riskCounts": risk_counts,
        "formulaNumerator": numerator,
        "formulaDenominator": denominator,
        "completedStatuses": list(COMPLETED_PROJECT_STATUSES),
        "newInDevelopment": new_in_development,
        "newCompleted": new_completed,
    }


# copied from weeklyreport
def get_view_name(lark_cli: str, as_identity: str, base_token: str, table_id: str, view_id: str) -> str:
    cmd = [
        lark_cli, "base", "+view-get",
        "--as", as_identity,
        "--base-token", base_token,
        "--table-id", table_id,
        "--view-id", view_id,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = redact_secret(proc.stderr or proc.stdout, base_token)
        raise SkillError(f"lark-cli view-get 失败：{detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise SkillError("lark-cli view-get 返回了无法解析的 JSON") from error
    if not isinstance(payload, dict):
        raise SkillError("lark-cli view-get 返回的 JSON 顶层不是对象")
    if not payload.get("ok"):
        message = lark_error_message(payload, base_token)
        raise SkillError(f"读取 Base 视图失败：{message}")
    return payload["data"]["view"]["name"]


# copied from weeklyreport（脱离 task_specs 依赖，改为通用整表扫描）
def scan_records(
    scan_view_id: str | None,
    scope: str,
    base_token: str,
    table_id: str,
    lark_cli: str,
    as_identity: str,
    page_delay: float,
    logs: list[str],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    offset = 0
    limit = 200
    while True:
        log(logs, f"分页读取 Base 记录（{scope}）：offset={offset}, limit={limit}")
        payload = run_lark_record_list(lark_cli, as_identity, base_token, table_id, offset, limit, scan_view_id)
        data = payload["data"]
        fields = data["fields"]
        rows = data["data"]
        record_ids = data.get("record_id_list", [])
        field_indexes = {field: index for index, field in enumerate(fields)}
        resolved_fields = resolve_field_names(fields)
        actual_to_canonical = {actual: canonical for canonical, actual in resolved_fields.items()}

        if offset == 0 and scan_view_id is None:
            missing_fields = [name for name in REQUIRED_FIELDS if name not in resolved_fields]
            if missing_fields:
                raise SkillError(
                    "Base 表缺少必需字段（已忽略末尾中文/英文括号备注仍未匹配到）："
                    + "、".join(missing_fields)
                )

        parent_actual = resolved_fields.get("父记录")
        for index, row in enumerate(rows):
            record = {
                actual_to_canonical.get(fields[i], fields[i]): normalize_cell_value(row[i])
                for i in range(min(len(fields), len(row)))
            }
            if index < len(record_ids):
                record["_record_id"] = str(record_ids[index])
            parent_index = field_indexes.get(parent_actual) if parent_actual else None
            if parent_index is not None and parent_index < len(row):
                record["_parent_ids"] = ",".join(extract_link_ids(row[parent_index]))
            records.append(record)

        if not data.get("has_more") or not rows:
            break
        offset += len(rows)
        if page_delay > 0:
            time.sleep(page_delay)
    return records


def match_scope_tasks(
    scope: dict[str, Any],
    view_records: list[dict[str, str]],
    all_records: list[dict[str, str]],
    logs: list[str],
) -> list[tuple[str, dict[str, str], dict[str, str]]]:
    """白名单（TDT 名 + 子任务名）-> [(tdt 名, TDT 记录, 子任务记录)]。"""
    parent_by_key: dict[str, dict[str, str]] = {}
    duplicate_parents: set[str] = set()
    for record in view_records:
        if not is_tdt_record(record):
            continue
        key = normalize_match_key(record.get("TDT/子任务名称", ""))
        if not key:
            continue
        if key in parent_by_key:
            duplicate_parents.add(record.get("TDT/子任务名称", ""))
            continue
        parent_by_key[key] = record
    if duplicate_parents:
        raise SkillError("视图中存在重复父级TDT：" + "，".join(sorted(duplicate_parents)))

    matched: list[tuple[str, dict[str, str], dict[str, str]]] = []
    missing: list[str] = []
    for entry in scope["tdts"]:
        tdt_name = entry["tdt"]
        parent = parent_by_key.get(normalize_match_key(tdt_name))
        if not parent:
            missing.append(f"父级TDT'{tdt_name}'不在视图中")
            continue
        parent_id = parent.get("_record_id", "")
        if not parent_id:
            raise SkillError(f"父级TDT'{tdt_name}'缺少 record_id，无法安全匹配子任务")
        for task_name in entry["tasks"]:
            task_key = normalize_match_key(task_name)
            hits = [
                child for child in all_records
                if is_child_task_record(child)
                and parent_id in {p for p in (child.get("_parent_ids") or "").split(",") if p}
                and normalize_match_key(child.get("TDT/子任务名称", "")) == task_key
            ]
            if not hits:
                missing.append(f"'{tdt_name}' 下未找到子任务'{task_name}'")
                continue
            if len(hits) > 1:
                raise SkillError(f"'{tdt_name}' 下子任务'{task_name}'存在 {len(hits)} 条重复精确匹配记录")
            matched.append((tdt_name, parent, hits[0]))
            log(logs, f"层级精确匹配成功：{tdt_name} / {hits[0].get('TDT/子任务名称', '')}（{hits[0].get('项目编码', '')}）")
    if missing:
        raise SkillError("白名单匹配失败：" + "；".join(missing))
    return matched


def resolve_record_key(records: list[dict[str, str]], wanted: str) -> str | None:
    """在记录键里按字段容差（忽略末尾括号备注）解析实际字段名。"""
    want = normalize_match_key(strip_field_suffix(wanted))
    for record in records:
        for key in record:
            if key.startswith("_"):
                continue
            if normalize_match_key(strip_field_suffix(key)) == want:
                return key
    return None


def match_field_tasks(
    filter_field: str,
    filter_value: str,
    all_records: list[dict[str, str]],
    logs: list[str],
) -> list[tuple[str, dict[str, str], dict[str, str]]]:
    """字段筛选模式：收录「filter_field == filter_value」的子任务记录。"""
    parents_by_id: dict[str, dict[str, str]] = {}
    for record in all_records:
        if not is_tdt_record(record):
            continue
        rid = record.get("_record_id")
        if rid:
            parents_by_id.setdefault(rid, record)

    key = resolve_record_key(all_records, filter_field)
    if not key:
        raise SkillError(f"Base 表中未找到筛选字段：{filter_field}")

    accepted = accepted_filter_values(filter_value)
    matched: list[tuple[str, dict[str, str], dict[str, str]]] = []
    orphaned: list[str] = []
    for child in all_records:
        if not is_child_task_record(child):
            continue
        if normalize_match_key((child.get(key, "") or "").strip()) not in accepted:
            continue
        parent: dict[str, str] = {}
        for pid in (child.get("_parent_ids") or "").split(","):
            if pid and pid in parents_by_id:
                parent = parents_by_id[pid]
                break
        if not parent:
            orphaned.append(
                (child.get("TDT/子任务名称", "") or "").strip()
                or (child.get("项目编码", "") or "").strip()
                or child.get("_record_id", "未知记录")
            )
            continue
        tdt_name = (parent.get("TDT/子任务名称", "") or "").strip()
        matched.append((tdt_name, parent, child))
        log(logs, f"字段筛选命中：{tdt_name} / {child.get('TDT/子任务名称', '')}（{child.get('项目编码', '')}）")
    if orphaned:
        raise SkillError(
            "字段筛选命中的子任务未通过「父记录」关联到 TDT 记录："
            + "、".join(orphaned)
        )
    if not matched:
        raise SkillError(f"没有子任务记录的「{filter_field}」为「{filter_value}」")
    return matched


def display_date(day: dt.date | None, run_date: dt.date) -> str:
    if day is None:
        return "—"
    if day.year != run_date.year:
        return f"{day.year % 100:02d}/{day.month:02d}/{day.day:02d}"
    return f"{day.month:02d}/{day.day:02d}"


def mapped_base_value(raw: Any) -> str:
    """运行时映射总原则：只清空真正空值，其他 Base 非空输入原样保留。"""
    if raw is None:
        return ""
    return str(raw).strip()


def display_compact_date(
    raw: str,
    warnings: list[str] | None = None,
    context: str = "日期字段",
) -> str:
    """正式版日期：合法值转 YY/MM/DD；无法解析的非空值保留原文。"""
    value = mapped_base_value(raw)
    if not value:
        return ""
    day = parse_base_date(value)
    if day:
        return day.strftime("%y/%m/%d")
    if warnings is not None:
        warnings.append(f"{context}无法解析为日期，已保留 Base 原文：{value}")
    return value


def display_issue_date(
    raw: str,
    warnings: list[str] | None = None,
    context: str = "问题日期字段",
) -> str:
    """问题清单日期：按参考表显示为 M月D日；无法解析时保留原值。"""
    value = mapped_base_value(raw)
    if not value:
        return ""
    day = parse_base_date(value)
    if day:
        return f"{day.month}月{day.day}日"
    if warnings is not None:
        warnings.append(f"{context}无法解析为日期，已保留 Base 原文：{value}")
    return value


def parse_issue_week(raw: str) -> int | None:
    """Base 数字字段 Week -> 1～53；空值或非法值返回 None。"""
    value = (raw or "").strip()
    try:
        number = float(value)
    except ValueError:
        return None
    week = int(number)
    return week if number == week and 1 <= week <= 53 else None


def first_record_value(record: dict[str, str], field_names: list[str]) -> str:
    """按兼容字段名顺序读取首个非空值，不把可选字段升级为全表必需字段。"""
    for field_name in field_names:
        key = resolve_record_key([record], field_name)
        if key:
            value = (record.get(key, "") or "").strip()
            if value:
                return value
    return ""


def build_milestone(lab: str, planned_raw: str, actual_raw: str, run_date: dt.date) -> dict[str, str]:
    planned = parse_base_date(planned_raw)
    actual = parse_base_date(actual_raw)
    if actual is not None:
        return {"lab": lab, "date": display_date(actual, run_date), "st": "done"}
    if planned is not None and planned < run_date:
        return {"lab": lab, "date": display_date(planned, run_date), "st": "late"}
    return {"lab": lab, "date": display_date(planned, run_date), "st": "pend"}


def build_project(record: dict[str, str], parent: dict[str, str], tdt_name: str, run_date: dt.date, warnings: list[str]) -> dict[str, Any]:
    task_name = record.get("TDT/子任务名称", "")
    stage = mapped_base_value(record.get(STAGE_FIELD, ""))
    risk = mapped_base_value(record.get("风险状态", ""))

    cps = parse_control_points(record.get(CONTROL_POINT_FIELD, ""))
    if not cps:
        warnings.append(f"子任务'{task_name}'的阶段控制点为空，控制点显示为空")

    current, next_plan = split_progress(record.get("最新进展描述", ""), run_date, warnings, task_name)
    risk_raw = mapped_base_value(record.get("项目风险", ""))
    if not risk_raw:
        risk_desc = ""
    else:
        risk_desc = format_numbered_spacing(
            risk_raw,
            add_blank_between_items=False,
            compact_visual_model_numbering=True,
        )

    # 分组键以「子任务 PM」为准（任务责任人）；缺失时回退 TDT PM
    pm = (
        (record.get("子任务 PM", "") or "").strip()
        or (record.get("TDT PM", "") or "").strip()
        or (parent.get("TDT PM", "") or "").strip()
        or "未指定"
    )

    upd_day = parse_base_date(record.get("最近更新时间", ""))
    tdt_summary = first_record_value(
        parent,
        ["价值说明", "价值目标", "产品摘要", "最新进展描述（TDT PM）"],
    )

    return {
        "pm": pm,
        "tdt": tdt_name,
        "name": task_name,
        "code": mapped_base_value(record.get("项目编码", "")),
        "stage": stage,
        "risk": risk,
        "upd": display_date(upd_day, run_date) if upd_day else "",
        "valueDecision": display_compact_date(
            first_record_value(record, [VALUE_DECISION_FIELD, "启动时间（价值决策）", "启动时间"]),
            warnings,
            f"子任务'{task_name}'的价值决策",
        ),
        "closeDate": display_compact_date(
            first_record_value(record, ["TDR3预计", "结项时间"]),
            warnings,
            f"子任务'{task_name}'的结项时间",
        ),
        "tdtSummary": tdt_summary,
        "cps": cps,
        "ms": [
            build_milestone("启动", "", record.get(VALUE_DECISION_FIELD, ""), run_date),
            build_milestone("TDR1", record.get("TDR1计划", ""), record.get("TDR1实际", ""), run_date),
            build_milestone("TDR2", record.get("TDR2(KO)", ""), record.get("TDR2实际", ""), run_date),
            build_milestone("TDR3", record.get("TDR3预计", ""), record.get("TDR3实际", ""), run_date),
        ],
        "week": to_items(current),
        "next": to_items(next_plan),
        "riskDesc": to_items(risk_desc),
    }


def group_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for project in projects:
        pm = project.pop("pm")
        if pm not in groups:
            groups[pm] = []
            order.append(pm)
        groups[pm].append(project)
    if "未指定" in order:
        order.remove("未指定")
        order.append("未指定")
    for pm in order:
        groups[pm].sort(key=lambda p: RISK_ORDER.get(p["risk"], 3))
    return [{"pm": pm, "projects": groups[pm]} for pm in order]


def build_issue_data(
    *,
    issue_base_url: str | None,
    lark_cli: str,
    as_identity: str,
    page_delay: float,
    run_date: dt.date,
    logs: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """读取问题 Base 指定视图，装配上一周遗留问题与当周新增问题。"""
    if not issue_base_url:
        return {
            "enabled": False,
            "week": None,
            "previousWeek": None,
            "weekLabel": "",
            "viewName": "",
            "groups": [],
            "previousTotal": 0,
            "currentTotal": 0,
            "total": 0,
            "open": 0,
            "closed": 0,
        }

    base_token, table_id, view_id = parse_base_link(issue_base_url)
    if not table_id or not view_id:
        raise SkillError("问题 Base URL 必须包含 table 与 view 查询参数")

    view_name = get_view_name(lark_cli, as_identity, base_token, table_id, view_id)
    log(logs, f"问题视图校验通过：{view_name}")

    sort_json = json.dumps(
        [{"field": "Week", "desc": True}, {"field": "Item", "desc": False}],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    current_iso_year, current_week, _ = run_date.isocalendar()
    previous_date = run_date - dt.timedelta(days=7)
    previous_iso_year, previous_week, _ = previous_date.isocalendar()
    records_by_week: dict[int, list[dict[str, str]]] = {
        previous_week: [],
        current_week: [],
    }
    offset = 0
    limit = 200

    while True:
        log(logs, f"分页读取问题记录：offset={offset}, limit={limit}")
        payload = run_lark_record_list(
            lark_cli,
            as_identity,
            base_token,
            table_id,
            offset,
            limit,
            view_id,
            field_ids=ISSUE_FIELDS,
            sort_json=sort_json,
        )
        data = payload["data"]
        fields = data["fields"]
        rows = data["data"]

        for row in rows:
            record = {
                fields[index]: normalize_cell_value(row[index])
                for index in range(min(len(fields), len(row)))
            }
            week = parse_issue_week(record.get("Week", ""))
            has_content = any(
                (record.get(field, "") or "").strip()
                for field in ISSUE_DISPLAY_FIELDS
            )
            if not has_content:
                # 仅填写 Week 的记录不生成问题内容；标准周次由 run_date 决定。
                continue
            if week is None:
                raw_week = (record.get("Week", "") or "").strip()
                record_label = (
                    mapped_base_value(record.get("TDT项目子任务名称", ""))
                    or mapped_base_value(record.get("Item", ""))
                    or "问题记录"
                )
                if raw_week:
                    warnings.append(
                        f"问题'{record_label}'的 Week 无法解析，已忽略该记录：{raw_week}"
                    )
                else:
                    warnings.append(
                        f"问题'{record_label}'的 Week 为空，已忽略该记录"
                    )
                continue
            if week in records_by_week:
                records_by_week[week].append(record)

        if not data.get("has_more") or not rows:
            break
        offset += len(rows)
        if page_delay > 0:
            time.sleep(page_delay)

    def build_items(records: list[dict[str, str]]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for record in records:
            status = mapped_base_value(record.get("任务状态", "")).upper()
            record_label = (
                mapped_base_value(record.get("TDT项目子任务名称", ""))
                or mapped_base_value(record.get("Item", ""))
                or "问题记录"
            )
            items.append(
                {
                    "item": mapped_base_value(record.get("Item", "")),
                    "taskName": mapped_base_value(record.get("TDT项目子任务名称", "")),
                    "task": mapped_base_value(record.get("任务", "")),
                    "progress": mapped_base_value(record.get("当前进展", "")),
                    "plannedDate": display_issue_date(
                        record.get("计划完成日期", ""),
                        warnings,
                        f"问题'{record_label}'的计划完成日期",
                    ),
                    "adjustedDate": display_issue_date(
                        record.get("调整日期", ""),
                        warnings,
                        f"问题'{record_label}'的调整日期",
                    ),
                    "actualDate": display_issue_date(
                        record.get("实际完成日期", ""),
                        warnings,
                        f"问题'{record_label}'的实际完成日期",
                    ),
                    "proposer": mapped_base_value(record.get("提出人", "")),
                    "department": mapped_base_value(record.get("责任部门", "")),
                    "owner": mapped_base_value(record.get("责任人", "")),
                    "status": status,
                }
            )
        return items

    if previous_iso_year == current_iso_year:
        previous_title = f"第{previous_week}周遗留问题"
        current_title = f"第{current_week}周新增问题"
        week_label = f"第{previous_week}周—第{current_week}周"
    else:
        previous_title = f"{previous_iso_year}年第{previous_week}周遗留问题"
        current_title = f"{current_iso_year}年第{current_week}周新增问题"
        week_label = (
            f"{previous_iso_year}年第{previous_week}周—"
            f"{current_iso_year}年第{current_week}周"
        )
    groups: list[dict[str, Any]] = [
        {
            "week": previous_week,
            "title": previous_title,
            "items": build_items(records_by_week[previous_week]),
        },
        {
            "week": current_week,
            "title": current_title,
            "items": build_items(records_by_week[current_week]),
        },
    ]

    for group in groups:
        group["total"] = len(group["items"])
        group["open"] = sum(1 for item in group["items"] if item["status"] == "OPEN")
        group["closed"] = sum(1 for item in group["items"] if item["status"] == "CLOSED")

    all_items = [item for group in groups for item in group["items"]]
    open_count = sum(1 for item in all_items if item["status"] == "OPEN")
    closed_count = sum(1 for item in all_items if item["status"] == "CLOSED")
    previous_total = groups[0]["total"] if len(groups) == 2 else 0
    current_total = groups[1]["total"] if len(groups) == 2 else len(all_items)
    log(
        logs,
        f"问题清单装配完成：{week_label}，上周 {previous_total} 条，当周 {current_total} 条",
    )
    return {
        "enabled": True,
        "week": current_week,
        "previousWeek": previous_week,
        "weekLabel": week_label,
        "viewName": view_name,
        "groups": groups,
        "previousTotal": previous_total,
        "currentTotal": current_total,
        "total": len(all_items),
        "open": open_count,
        "closed": closed_count,
    }


def build_data(
    *,
    base_url: str,
    issue_base_url: str | None = None,
    innovation_base_url: str | None = None,
    lark_cli: str,
    as_identity: str,
    page_delay: float,
    scope: dict[str, Any] | None,
    pm_roster: list[str],
    filter_field: str | None,
    filter_value: str,
    run_date: dt.date,
    logs: list[str],
    warnings: list[str],
    meeting_discipline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从 Base 拉取并装配看板 DATA（静态生成与本地服务共用）。"""
    base_token, table_id, view_id = parse_base_link(base_url)
    if not table_id or not view_id:
        raise SkillError("Base URL 必须包含 table 与 view 查询参数")

    view_name = get_view_name(lark_cli, as_identity, base_token, table_id, view_id)
    if view_name != EXPECTED_VIEW_NAME:
        raise SkillError(f"视图名不符：期望'{EXPECTED_VIEW_NAME}'，实际'{view_name}'，请检查 URL")
    log(logs, f"视图校验通过：{view_name}")

    field_payload = run_lark_field_list(lark_cli, as_identity, base_token, table_id)
    field_option_orders = extract_field_option_orders(
        field_payload,
        ("赛道", PRODUCT_GENERATION_FIELD),
    )
    all_records = scan_records(None, "全表记录", base_token, table_id, lark_cli, as_identity, page_delay, logs)
    if all_records:
        field_names = [
            str(field.get("name", ""))
            for field in field_payload.get("data", {}).get("fields", [])
            if isinstance(field, dict)
        ]
        primary_field_name = resolve_field_names(field_names).get("TDT/子任务名称")
        if not primary_field_name:
            raise SkillError("Base 表缺少必需字段：TDT/子任务名称")
        created_times = scan_record_created_times(
            base_token=base_token,
            table_id=table_id,
            primary_field_name=primary_field_name,
            lark_cli=lark_cli,
            as_identity=as_identity,
            page_delay=page_delay,
            logs=logs,
        )
        for record in all_records:
            record_id = (record.get("_record_id", "") or "").strip()
            record["_created_time"] = created_times.get(record_id, "")

    if filter_field:
        matched = match_field_tasks(filter_field, filter_value, all_records, logs)
    else:
        view_records = scan_records(view_id, "目标视图", base_token, table_id, lark_cli, as_identity, page_delay, logs)
        matched = match_scope_tasks(scope, view_records, all_records, logs)

    projects = [build_project(child, parent, tdt, run_date, warnings) for tdt, parent, child in matched]
    groups = group_projects(projects)
    project_overview = build_project_overview(
        records=all_records,
        logs=logs,
        field_option_orders=field_option_orders,
        run_date=run_date,
        warnings=warnings,
    )
    development_summary = build_development_summary(all_records, logs)

    # 全表「子任务 PM」名单（去重、按出现顺序），供人名滑动条类模板使用
    all_pms: list[str] = []
    seen_pms: set[str] = set()
    for record in all_records:
        if not is_child_task_record(record):
            continue
        for name in (record.get("子任务 PM", "") or "").split("、"):
            name = name.strip()
            if name and name not in seen_pms:
                seen_pms.add(name)
                all_pms.append(name)

    iso_year, iso_week, _ = run_date.isocalendar()
    issues = build_issue_data(
        issue_base_url=issue_base_url,
        lark_cli=lark_cli,
        as_identity=as_identity,
        page_delay=page_delay,
        run_date=run_date,
        logs=logs,
        warnings=warnings,
    )
    innovation_competition = build_innovation_competition(
        innovation_base_url=innovation_base_url,
        lark_cli=lark_cli,
        as_identity=as_identity,
        page_delay=page_delay,
        logs=logs,
        warnings=warnings,
    )
    return {
        "dashboardYear": run_date.year,
        "week": f"{iso_year} · W{iso_week:02d}",
        "generatedAt": dt.datetime.now().strftime("%m-%d %H:%M"),
        "viewName": view_name,
        "allPms": all_pms,
        "pmRoster": pm_roster,
        "groups": groups,
        "projectOverview": project_overview,
        "innovationCompetition": innovation_competition,
        "developmentSummary": development_summary,
        "issues": issues,
        "meetingDiscipline": meeting_discipline or {"enabled": False, "sections": []},
    }


def build_innovation_competition(
    *,
    innovation_base_url: str | None,
    lark_cli: str,
    as_identity: str,
    page_delay: float,
    logs: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """从独立 Base 视图读取并装配创新大赛项目概况。"""
    if not innovation_base_url:
        return {
            "enabled": False,
            "sourceLinked": False,
            "viewName": "",
            "riskSummary": "",
            "total": 0,
            "inProgress": 0,
            "completed": 0,
            "canceled": 0,
            "lowRisk": 0,
            "mediumRisk": 0,
            "highRisk": 0,
            "projects": [],
        }

    base_token, table_id, view_id = parse_base_link(innovation_base_url)
    if not table_id or not view_id:
        raise SkillError("创新大赛 Base URL 必须包含 table 与 view 查询参数")
    view_name = get_view_name(lark_cli, as_identity, base_token, table_id, view_id)

    field_payload = run_lark_field_list(lark_cli, as_identity, base_token, table_id)
    raw_fields = field_payload.get("data", {}).get("fields", [])
    fields_by_name = {
        str(field.get("name", "")).strip(): field
        for field in raw_fields
        if isinstance(field, dict) and str(field.get("name", "")).strip()
    }
    missing_fields = [name for name in INNOVATION_FIELDS if name not in fields_by_name]
    if missing_fields:
        raise SkillError("创新大赛 Base 表缺少必需字段：" + "、".join(missing_fields))
    selected_field_names = list(INNOVATION_FIELDS)
    if INNOVATION_ORDER_FIELD in fields_by_name:
        selected_field_names.append(INNOVATION_ORDER_FIELD)
    field_ids = [str(fields_by_name[name]["id"]) for name in selected_field_names]

    records: list[dict[str, str]] = []
    offset = 0
    limit = 200
    while True:
        log(logs, f"分页读取创新大赛视图：offset={offset}, limit={limit}")
        payload = run_lark_record_list(
            lark_cli,
            as_identity,
            base_token,
            table_id,
            offset,
            limit,
            view_id,
            field_ids=field_ids,
        )
        data = payload.get("data", {})
        returned_fields = data.get("fields", [])
        rows = data.get("data", [])
        for row in rows:
            record = {
                str(returned_fields[index]): normalize_cell_value(row[index]).strip()
                for index in range(min(len(returned_fields), len(row)))
            }
            if any(record.get(name, "") for name in INNOVATION_FIELDS):
                records.append(record)
        if not data.get("has_more") or not rows:
            break
        offset += len(rows)
        if page_delay > 0:
            time.sleep(page_delay)

    projects = []
    for source_index, record in enumerate(records):
        raw_order = record.get(INNOVATION_ORDER_FIELD, "")
        try:
            order = float(raw_order)
        except (TypeError, ValueError):
            order = None
        projects.append({
            "name": mapped_base_value(record.get("项目名称", "")),
            "track": mapped_base_value(record.get("技术赛道", "")),
            "stage": mapped_base_value(record.get("项目阶段", "")),
            "status": mapped_base_value(record.get("项目状态", "")),
            "risk": mapped_base_value(record.get("项目风险", "")),
            "order": order,
            "sourceIndex": source_index,
        })
    projects.sort(
        key=lambda project: (
            project["order"] is None,
            project["order"] if project["order"] is not None else 0,
            project["sourceIndex"],
        )
    )
    for project in projects:
        project.pop("order", None)
        project.pop("sourceIndex", None)
    in_progress = sum(project["status"] == INNOVATION_IN_PROGRESS_STATUS for project in projects)
    completed = sum(project["status"] == INNOVATION_COMPLETED_STATUS for project in projects)
    canceled = sum(project["status"] == INNOVATION_CANCELED_STATUS for project in projects)
    low_risk = sum(project["risk"] == "低风险" for project in projects)
    medium_risk = sum(project["risk"] == "中风险" for project in projects)
    high_risk = sum(project["risk"] == "高风险" for project in projects)

    allowed_statuses = {
        INNOVATION_IN_PROGRESS_STATUS,
        INNOVATION_COMPLETED_STATUS,
        INNOVATION_CANCELED_STATUS,
    }
    invalid_status_projects = [project["name"] or "未命名项目" for project in projects if project["status"] not in allowed_statuses]
    if invalid_status_projects:
        warnings.append(
            "创新大赛项目状态不是进行中／已完成／已取消：" + "、".join(invalid_status_projects)
        )
    invalid_risk_projects = [
        project["name"] or "未命名项目"
        for project in projects
        if project["risk"] not in {"低风险", "中风险", "高风险"}
    ]
    if invalid_risk_projects:
        warnings.append("创新大赛项目风险不是低／中／高风险：" + "、".join(invalid_risk_projects))

    if projects and low_risk == len(projects):
        risk_summary = "均正常"
    else:
        risk_parts = []
        if medium_risk:
            risk_parts.append(f"中风险项目{medium_risk}个")
        if high_risk:
            risk_parts.append(f"高风险项目{high_risk}个")
        risk_summary = "其中" + "、".join(risk_parts) if risk_parts else ""

    log(
        logs,
        "创新大赛概况装配完成："
        f"项目 {len(projects)} 个，进行中 {in_progress} 个，已完成 {completed} 个，"
        f"已取消 {canceled} 个，中风险 {medium_risk} 个，高风险 {high_risk} 个",
    )
    return {
        "enabled": True,
        "sourceLinked": True,
        "viewName": view_name,
        "riskSummary": risk_summary,
        "total": len(projects),
        "inProgress": in_progress,
        "completed": completed,
        "canceled": canceled,
        "lowRisk": low_risk,
        "mediumRisk": medium_risk,
        "highRisk": high_risk,
        "projects": projects,
    }


def load_dashboard_config(config_path: Path) -> list[str]:
    """读取正式看板配置；当前只允许 PM 固定相对顺序。"""
    if not config_path.exists():
        raise SkillError(f"正式配置文件不存在：{config_path}（格式见 dashboard_config.example.json）")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SkillError(f"正式配置 JSON 无效：{config_path}（{error}）") from error
    if not isinstance(config, dict):
        raise SkillError(f"正式配置顶层必须是对象：{config_path}")
    unexpected = sorted(set(config) - {"pm_roster"})
    if unexpected:
        raise SkillError(f"正式配置包含未支持字段：{'、'.join(unexpected)}（{config_path}）")
    pm_roster = config.get("pm_roster")
    if not isinstance(pm_roster, list) or not pm_roster:
        raise SkillError(f"正式配置 pm_roster 必须是非空姓名字符串列表：{config_path}")
    normalized = [name.strip() for name in pm_roster if isinstance(name, str) and name.strip()]
    if len(normalized) != len(pm_roster):
        raise SkillError(f"正式配置 pm_roster 必须全部为非空姓名字符串：{config_path}")
    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise SkillError(f"正式配置 pm_roster 存在重复姓名：{'、'.join(duplicates)}（{config_path}）")
    return normalized


def load_scope_file(scope_path: Path) -> dict[str, Any]:
    """读取旧白名单兼容配置；正式字段筛选模式不调用。"""
    if not scope_path.exists():
        raise SkillError(f"白名单文件不存在：{scope_path}（格式见 demo_scope.example.json）")
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SkillError(f"白名单配置 JSON 无效：{scope_path}（{error}）") from error
    if not isinstance(scope, dict):
        raise SkillError(f"白名单配置顶层必须是对象：{scope_path}")
    tdts = scope.get("tdts")
    if not isinstance(tdts, list) or not tdts:
        raise SkillError(f"白名单文件缺少 tdts 列表：{scope_path}")
    for index, entry in enumerate(tdts, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("tdt"), str) or not entry["tdt"].strip():
            raise SkillError(f"白名单 tdts 第 {index} 项缺少有效 tdt 名称：{scope_path}")
        tasks = entry.get("tasks")
        if not isinstance(tasks, list) or not tasks or not all(isinstance(task, str) and task.strip() for task in tasks):
            raise SkillError(f"白名单 tdts 第 {index} 项缺少有效 tasks 列表：{scope_path}")
    return scope


def load_meeting_discipline(path: Path) -> dict[str, Any]:
    """读取会议内容配置并装配为正式会议纪律数据。"""
    if not path.exists():
        return {"enabled": False, "sections": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SkillError(f"会议纪律配置 JSON 无效：{path}（{error}）") from error
    sections = raw.get("sections") if isinstance(raw, dict) else None
    if not isinstance(sections, list) or not sections:
        raise SkillError(f"会议纪律配置缺少 sections 列表：{path}")
    return {"enabled": True, "sections": sections}


def inject_template(template_path: Path, data: dict[str, Any]) -> str:
    template = template_path.read_text(encoding="utf-8")
    placeholder = "/*__DATA__*/null"
    placeholder_count = template.count(placeholder)
    if placeholder_count != 1:
        raise SkillError(f"模板必须且只能包含一个数据占位符 {placeholder}：{template_path}（实际 {placeholder_count} 个）")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace(placeholder, payload)


def offline_snapshot_filename(run_date: dt.date) -> str:
    """返回正式离线看板文件名，周次使用两位 ISO 周次。"""
    _, iso_week, _ = run_date.isocalendar()
    return f"{run_date.isoformat()}(W{iso_week:02d})-TDT技术项目状态看板.html"


def main() -> int:
    src_dir = Path(__file__).resolve().parent
    project_dir = src_dir.parent

    parser = argparse.ArgumentParser(description="Generate TDT weekly-meeting dashboard HTML from Feishu Base")
    parser.add_argument("--base-url", required=True, help="Base URL with table and view query params")
    parser.add_argument("--issue-base-url", default=None, help="Optional issue-list Base URL with table and view query params")
    parser.add_argument("--innovation-base-url", default=None, help="Optional innovation-project Base URL with table and view query params")
    parser.add_argument("--lark-cli", default="lark-cli", help="Path/name of lark-cli executable")
    parser.add_argument("--as", dest="as_identity", default="user", choices=["user", "bot"], help="lark-cli identity")
    parser.add_argument("--page-delay", type=float, default=0.2, help="Seconds between Base record-list pages")
    parser.add_argument("--run-date", default=None, help="Override run date YYYY-MM-DD (used in filename and late-judgement)")
    parser.add_argument("--output-dir", default=str(project_dir / "output"), help="Output directory")
    parser.add_argument("--config", default=str(src_dir / "dashboard_config.json"), help="Formal dashboard config JSON path")
    parser.add_argument("--scope", default=None, help="Legacy whitelist JSON path; required only without --filter-field")
    parser.add_argument(
        "--meeting-discipline",
        default=str(src_dir / "meeting_content.json"),
        help="Meeting-content JSON path",
    )
    parser.add_argument("--filter-field", default=None, help="按字段筛选收录子任务（替代白名单），如：是否上周三例会")
    parser.add_argument("--filter-value", default="是", help="筛选字段的命中值，默认「是」（勾选框 True 亦命中）")
    parser.add_argument("--template", default=str(src_dir / "template-dashboard-v1.3.0.html"), help="Template HTML path")
    parser.add_argument("--variant", default="v1.3.0", help="Legacy compatibility option; formal offline filename is fixed")
    args = parser.parse_args()

    logs: list[str] = []
    warnings: list[str] = []

    run_date = dt.date.fromisoformat(args.run_date) if args.run_date else dt.date.today()
    pm_roster = load_dashboard_config(Path(args.config))
    scope = load_scope_file(Path(args.scope)) if args.scope else None
    if not args.filter_field and scope is None:
        raise SkillError("未设置 --filter-field 时必须同时传入旧白名单 --scope")
    meeting_discipline = load_meeting_discipline(Path(args.meeting_discipline))

    data = build_data(
        base_url=args.base_url,
        lark_cli=args.lark_cli,
        as_identity=args.as_identity,
        page_delay=args.page_delay,
        scope=scope,
        pm_roster=pm_roster,
        filter_field=args.filter_field,
        filter_value=args.filter_value,
        run_date=run_date,
        logs=logs,
        warnings=warnings,
        issue_base_url=args.issue_base_url,
        innovation_base_url=args.innovation_base_url,
        meeting_discipline=meeting_discipline,
    )

    html = inject_template(Path(args.template), data)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / offline_snapshot_filename(run_date)
    output_path.write_text(html, encoding="utf-8")
    log(logs, f"看板已生成：{output_path}")

    report = {
        "run_date": run_date.isoformat(),
        "view": data["viewName"],
        "matched": [
            {"tdt": p["tdt"], "task": p["name"], "code": p["code"]}
            for g in data["groups"] for p in g["projects"]
        ],
        "groups": [{"pm": g["pm"], "count": len(g["projects"])} for g in data["groups"]],
        "project_overview": {
            "enabled": data["projectOverview"]["enabled"],
            "total": data["projectOverview"]["total"],
            "track_count": data["projectOverview"]["trackCount"],
            "unassigned_count": data["projectOverview"]["unassignedCount"],
            "tracks": data["projectOverview"]["tracks"],
            "product_generations": data["projectOverview"]["productGenerations"],
            "unmapped_product_generation_options": data["projectOverview"]["unmappedProductGenerationOptions"],
            "weekly_addition": data["projectOverview"]["weeklyAddition"],
        },
        "innovation_competition": {
            "enabled": data["innovationCompetition"]["enabled"],
            "source_linked": data["innovationCompetition"]["sourceLinked"],
            "view": data["innovationCompetition"]["viewName"],
            "risk_summary": data["innovationCompetition"]["riskSummary"],
            "total": data["innovationCompetition"]["total"],
            "in_progress": data["innovationCompetition"]["inProgress"],
            "completed": data["innovationCompetition"]["completed"],
            "canceled": data["innovationCompetition"]["canceled"],
            "low_risk": data["innovationCompetition"]["lowRisk"],
            "medium_risk": data["innovationCompetition"]["mediumRisk"],
            "high_risk": data["innovationCompetition"]["highRisk"],
        },
        "issues": {
            "enabled": data["issues"]["enabled"],
            "week": data["issues"]["week"],
            "previous_week": data["issues"]["previousWeek"],
            "count": data["issues"]["total"],
            "open": data["issues"]["open"],
            "closed": data["issues"]["closed"],
            "groups": [
                {
                    "week": group["week"],
                    "title": group["title"],
                    "count": group["total"],
                    "open": group["open"],
                    "closed": group["closed"],
                }
                for group in data["issues"]["groups"]
            ],
        },
        "meeting_discipline": {
            "enabled": data["meetingDiscipline"]["enabled"],
            "sections": len(data["meetingDiscipline"]["sections"]),
        },
        "warnings": warnings,
        "logs": logs,
    }
    report_path = output_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"执行报告：{report_path}")

    if warnings:
        print("警告：")
        for item in warnings:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SkillError as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
