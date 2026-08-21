#!/usr/bin/env python3
"""Deterministic no-network simulation for refresh_stage_snapshot.py."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("refresh_stage_snapshot.py")
SPEC = importlib.util.spec_from_file_location("refresh_stage_snapshot", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载 refresh_stage_snapshot.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def expect_error(callable_object, expected_text: str) -> None:
    try:
        callable_object()
    except MODULE.SnapshotError as error:
        assert expected_text in str(error), str(error)
    else:
        raise AssertionError(f"期望 SnapshotError：{expected_text}")


def main() -> int:
    now = dt.datetime(2026, 7, 21, 8, 30, tzinfo=MODULE.TIMEZONE)
    last_week = dt.datetime(2026, 7, 14, 8, 30, tzinfo=MODULE.TIMEZONE)
    records = [
        MODULE.StageRecord(
            "rec_a", "任务 A", "开发阶段", ("开发阶段",), "计划阶段", last_week
        ),
        MODULE.StageRecord("rec_b", "任务 B", None, (), "概念阶段", last_week),
        MODULE.StageRecord(
            "rec_c", "任务 C", "技术迁移", ("技术迁移",), "开发阶段", last_week
        ),
    ]
    options = ("概念阶段", "计划阶段", "开发阶段", "技术迁移")
    plan = MODULE.build_plan(records, options, now)
    assert plan.nonblank_count == 2
    assert len(plan.blank_records) == 1
    assert plan.current_week_count == 0

    required = MODULE.RequiredFields(
        MODULE.FieldSpec(
            "fld_type", MODULE.RECORD_TYPE_FIELD, "select", (MODULE.CHILD_RECORD_TYPE,)
        ),
        MODULE.FieldSpec("fld_name", MODULE.TASK_NAME_FIELD, "text"),
        MODULE.FieldSpec("fld_source", MODULE.SOURCE_STAGE_FIELD, "lookup"),
        MODULE.FieldSpec("fld_snapshot", MODULE.SNAPSHOT_STAGE_FIELD, "select", options),
        MODULE.FieldSpec("fld_date", MODULE.SNAPSHOT_DATE_FIELD, "datetime"),
        "opt_child",
    )
    updates = MODULE.build_update_records(plan, required)
    assert len(updates) == 3
    assert updates[0]["fields"][MODULE.SNAPSHOT_STAGE_FIELD] == "开发阶段"
    assert updates[1]["fields"][MODULE.SNAPSHOT_STAGE_FIELD] is None
    assert isinstance(updates[0]["fields"][MODULE.SNAPSHOT_DATE_FIELD], int)

    after = [
        MODULE.StageRecord(
            "rec_a", "任务 A", "开发阶段", ("开发阶段",), "开发阶段", now
        ),
        MODULE.StageRecord("rec_b", "任务 B", None, (), None, now),
        MODULE.StageRecord(
            "rec_c", "任务 C", "技术迁移", ("技术迁移",), "技术迁移", now
        ),
    ]
    assert MODULE.verification_errors(plan, after) == []

    stale_after = [
        MODULE.StageRecord(
            "rec_a", "任务 A", "技术迁移", ("技术迁移",), "开发阶段", last_week
        ),
        *after[1:],
    ]
    stale_errors = MODULE.verification_errors(plan, stale_after)
    assert any("写入期间阶段查找发生变化" in error for error in stale_errors)
    assert any("不是本次执行时间" in error for error in stale_errors)

    repeated_records = [
        MODULE.StageRecord(
            record.record_id,
            record.task_name,
            record.source_stage,
            record.source_values,
            record.snapshot_stage,
            now,
        )
        for record in records
    ]
    repeated_plan = MODULE.build_plan(repeated_records, options, now)
    normal_args = argparse.Namespace(
        execute=True,
        force_replace_this_week=False,
        reason="",
        confirm=MODULE.NORMAL_CONFIRMATION,
    )
    expect_error(
        lambda: MODULE.validate_execution_gate(normal_args, repeated_plan),
        "默认禁止重复执行",
    )

    force_args = argparse.Namespace(
        execute=True,
        force_replace_this_week=True,
        reason="上次验证中断，外部导入尚未开始",
        confirm=MODULE.FORCE_CONFIRMATION,
    )
    MODULE.validate_execution_gate(force_args, repeated_plan)

    bad_records = records + [
        MODULE.StageRecord(
            "rec_bad",
            "异常任务",
            None,
            ("开发阶段", "技术迁移"),
            None,
            last_week,
        )
    ]
    expect_error(lambda: MODULE.build_plan(bad_records, options, now), "阶段查找为多值")

    print(
        "模拟验证通过：正常复制、空值清空、写后核验、同周拦截、强制覆盖和多值异常均符合预期。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
