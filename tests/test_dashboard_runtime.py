from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

import generate_dashboard as gd  # noqa: E402
import serve_dashboard as server  # noqa: E402


class LocalServiceIdentityTests(unittest.TestCase):
    def test_health_endpoint_identifies_project_01_and_current_build(self) -> None:
        httpd = server.DashboardHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.handle_request)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/health",
                timeout=2,
            ) as response:
                payload = json.load(response)
        finally:
            thread.join(timeout=2)
            httpd.server_close()

        self.assertEqual("ok", payload["status"])
        self.assertEqual("tdt-project-status-dashboard", payload["project_id"])
        self.assertEqual(server.BUILD_ID, payload["build_id"])

    def test_default_port_range_is_reserved_for_project_01(self) -> None:
        self.assertEqual(range(8710, 8720), server.DEFAULT_PORTS)

    def test_reused_service_opens_a_build_specific_url(self) -> None:
        argv = [
            "serve_dashboard.py",
            "--base-url",
            "https://example.invalid/base/token?table=table&view=view",
            "--auto-port",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(server, "choose_service_port", return_value=("reuse", 8710)),
            mock.patch.object(server.webbrowser, "open") as open_browser,
        ):
            result = server.main()

        self.assertEqual(0, result)
        open_browser.assert_called_once_with(
            f"http://127.0.0.1:8710/?build={server.BUILD_ID}"
        )

    def test_port_selector_prefers_running_current_build_over_earlier_free_port(self) -> None:
        states = {8710: "occupied", 8711: "free", 8712: "current"}

        result = server.choose_service_port(
            ports=range(8710, 8713),
            inspect=lambda candidate: states[candidate],
        )

        self.assertEqual(("reuse", 8712), result)

    def test_launchers_enable_project_specific_auto_port_selection(self) -> None:
        for name in (
            "start-dashboard.cmd",
            "start-dashboard.example.cmd",
            "start-dashboard.command",
            "start-dashboard.example.command",
        ):
            content = (PROJECT_DIR / name).read_text(encoding="utf-8")
            self.assertIn("--auto-port", content, name)
            self.assertIn("template-dashboard-v1.3.0.html", content, name)

    def test_launcher_line_endings_match_each_platform(self) -> None:
        for name in ("start-dashboard.cmd", "start-dashboard.example.cmd"):
            content = (PROJECT_DIR / name).read_bytes()
            self.assertIn(b"\r\n", content, name)
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""), name)
        for name in ("start-dashboard.command", "start-dashboard.example.command"):
            content = (PROJECT_DIR / name).read_bytes()
            self.assertIn(b"\n", content, name)
            self.assertNotIn(b"\r\n", content, name)


class MappedBaseValueTests(unittest.TestCase):
    def test_mapped_base_value_preserves_every_nonempty_base_value(self) -> None:
        for value in (None, "", "   "):
            self.assertEqual(gd.mapped_base_value(value), "")
        for raw, expected in (
            ("/", "/"),
            (" / ", "/"),
            ("／", "／"),
            ("-", "-"),
            ("--", "--"),
            ("—", "—"),
            ("–", "–"),
            ("未填写", "未填写"),
            ("暂无", "暂无"),
            ("无", "无"),
            ("A/B", "A/B"),
            ("正文 / 内容", "正文 / 内容"),
            ("暂无结论", "暂无结论"),
            (0, "0"),
            (False, "False"),
        ):
            self.assertEqual(gd.mapped_base_value(raw), expected)

    def test_value_mapping_does_not_change_explicit_business_scope_rules(self) -> None:
        self.assertEqual(gd.OVERVIEW_TRACK_TEXT_COUNT, 13)

        latest = gd.select_latest_progress_block(
            "7/1：旧日期内容；7/8：最新日期内容",
            dt.date(2026, 7, 22),
            [],
            "边界测试",
        )
        self.assertEqual(latest, "最新日期内容")

        project = gd.build_project(
            {
                "TDT/子任务名称": "PM边界测试",
                "子任务 PM": "",
                "TDT PM": "子记录TDT PM",
                gd.CONTROL_POINT_FIELD: "",
                "最新进展描述": "",
            },
            {"TDT PM": "父记录TDT PM"},
            "测试TDT",
            dt.date(2026, 7, 22),
            [],
        )
        self.assertEqual(project["pm"], "子记录TDT PM")

    def test_dates_preserve_unparseable_nonempty_values_and_progress_keeps_slash(self) -> None:
        warnings: list[str] = []
        self.assertEqual(gd.display_compact_date(""), "")
        self.assertEqual(gd.display_compact_date("2026-07-22"), "26/07/22")
        self.assertEqual(gd.display_compact_date("/", warnings, "价值决策"), "/")
        self.assertEqual(gd.display_issue_date(""), "")
        self.assertEqual(gd.display_issue_date("2026-07-22"), "7月22日")
        self.assertEqual(gd.display_issue_date("—", warnings, "计划完成日期"), "—")
        self.assertEqual(gd.format_numbered_spacing("", False), "")
        self.assertEqual(gd.format_numbered_spacing("/", False), "/")
        self.assertEqual(gd.split_progress("", dt.date(2026, 7, 22), [], "测试任务"), ("", ""))
        self.assertTrue(any("价值决策无法解析" in warning for warning in warnings))
        self.assertTrue(any("计划完成日期无法解析" in warning for warning in warnings))

    def test_progress_and_risk_keep_compact_visual_model_numbers(self) -> None:
        self.assertEqual(
            gd.format_numbered_spacing(
                "2.5D视觉模型说明",
                add_blank_between_items=False,
                compact_visual_model_numbering=True,
            ),
            "2.5D视觉模型说明",
        )

        project = gd.build_project(
            {
                "TDT/子任务名称": "视觉模型容错测试",
                "子任务 PM": "测试 PM",
                gd.CONTROL_POINT_FIELD: "",
                "最新进展描述": (
                    "07/29：本周进展：1.2D模型验证；2.3D效果评审；3.2.5D资源导入；4.4D方案归档"
                    "\n下周计划：1.2.5D模型优化"
                ),
                "项目风险": "1.2D风险确认；2.3D风险跟踪；3.2.5D资源风险",
            },
            {},
            "测试 TDT",
            dt.date(2026, 7, 29),
            [],
        )

        self.assertEqual(project["week"], ["1. 2D模型验证；", "2. 3D效果评审；", "3. 2.5D资源导入；", "4. 4D方案归档"])
        self.assertEqual(project["next"], ["1. 2.5D模型优化"])
        self.assertEqual(project["riskDesc"], ["1. 2D风险确认；", "2. 3D风险跟踪；", "3. 2.5D资源风险"])

    def test_project_table_fields_preserve_nonempty_base_values(self) -> None:
        record = {
            "TDT/子任务名称": "空值测试",
            "项目编码": "/",
            gd.STAGE_FIELD: "/",
            "风险状态": "/",
            gd.CONTROL_POINT_FIELD: "/",
            "最新进展描述": "",
            gd.VALUE_DECISION_FIELD: "/",
            "TDR3预计": "—",
            "项目风险": "/",
        }
        warnings: list[str] = []
        project = gd.build_project(record, {}, "测试TDT", dt.date(2026, 7, 22), warnings)
        self.assertEqual(project["code"], "/")
        self.assertEqual(project["stage"], "/")
        self.assertEqual(project["risk"], "/")
        self.assertEqual(project["valueDecision"], "/")
        self.assertEqual(project["closeDate"], "—")
        self.assertEqual(project["cps"], ["/"])
        self.assertEqual(project["week"], [])
        self.assertEqual(project["next"], [])
        self.assertEqual(project["riskDesc"], ["/"])
        self.assertEqual(sum("已保留 Base 原文" in warning for warning in warnings), 2)

    def test_development_table_preserves_nonempty_base_values(self) -> None:
        summary = gd.build_development_summary(
            [{
                "TDT/子任务": "子任务",
                gd.STAGE_COMPARISON_FIELD: "新增开发中",
                "赛道": "/",
                "TDT/子任务名称": "未填写",
            }],
            [],
        )
        self.assertEqual(summary["newInDevelopment"], [{"track": "/", "name": "未填写"}])

    def test_product_generation_multiselect_counts_each_selected_brand_once(self) -> None:
        selected_values = gd.normalize_cell_value([
            {"name": "GT 60"},
            {"name": "Pova 9"},
        ])
        self.assertEqual(selected_values, "GT 60、Pova 9")

        overview = gd.build_project_overview(
            records=[
                {"TDT/子任务": "子任务", gd.PRODUCT_GENERATION_FIELD: selected_values},
                {"TDT/子任务": "子任务", gd.PRODUCT_GENERATION_FIELD: "GT 60、Note 70"},
                {"TDT/子任务": "子任务", gd.PRODUCT_GENERATION_FIELD: "Pova 9、Pova 9"},
            ],
            logs=[],
            field_option_orders={
                gd.PRODUCT_GENERATION_FIELD: ["GT 60", "N代基线", "Note 70", "Camon 60", "Pova 9"],
            },
            run_date=dt.date(2026, 8, 13),
            warnings=[],
        )

        self.assertEqual(
            overview["productGenerations"],
            [
                {"key": "GT", "name": "GT", "label": "GT", "count": 2},
                {"key": "NOTE", "name": "NOTE", "label": "NOTE", "count": 1},
                {"key": "POVA", "name": "POVA", "label": "POVA", "count": 2},
            ],
        )

    def test_weekly_addition_counts_all_new_records_but_reports_only_filled_tracks(self) -> None:
        def created_time(value: str) -> str:
            return str(int(dt.datetime.fromisoformat(value).timestamp() * 1000))

        records = [
            {
                "TDT/子任务": "子任务",
                "TDT/子任务名称": "硬件一",
                "项目编码": "TDT-001",
                "赛道": "硬件系统",
                "_created_time": created_time("2026-08-10T09:00:00+08:00"),
            },
            {
                "TDT/子任务": "子任务",
                "TDT/子任务名称": "AI一",
                "项目编码": "TDT-002",
                "赛道": "AI",
                "_created_time": created_time("2026-08-11T09:00:00+08:00"),
            },
            {
                "TDT/子任务": "子任务",
                "TDT/子任务名称": "缺赛道",
                "项目编码": "TDT-003",
                "赛道": "",
                "_created_time": created_time("2026-08-12T09:00:00+08:00"),
            },
            {
                "TDT/子任务": "子任务",
                "TDT/子任务名称": "上周项目",
                "项目编码": "TDT-004",
                "赛道": "通信",
                "_created_time": created_time("2026-08-09T09:00:00+08:00"),
            },
        ]
        warnings: list[str] = []

        overview = gd.build_project_overview(
            records=records,
            logs=[],
            field_option_orders={"赛道": ["硬件系统", "AI", "通信"]},
            run_date=dt.date(2026, 8, 13),
            warnings=warnings,
        )

        self.assertEqual(overview["weeklyAddition"], {
            "total": 3,
            "tracks": [
                {"key": "硬件系统", "name": "硬件系统", "label": "硬件系统", "count": 1},
                {"key": "AI", "name": "AI", "label": "AI", "count": 1},
            ],
            "missingTrackCount": 1,
            "missingTrackProjects": [{"code": "TDT-003", "name": "缺赛道"}],
            "invalidCreatedTimeCount": 0,
            "invalidCreatedTimeProjects": [],
        })
        self.assertTrue(any("TDT-003 缺赛道" in warning for warning in warnings))

    def test_weekly_addition_omits_invalid_created_times_and_warns(self) -> None:
        warnings: list[str] = []
        overview = gd.build_project_overview(
            records=[{
                "TDT/子任务": "子任务",
                "TDT/子任务名称": "时间异常",
                "项目编码": "TDT-005",
                "赛道": "AI",
                "_created_time": "not-a-time",
            }],
            logs=[],
            field_option_orders={"赛道": ["AI"]},
            run_date=dt.date(2026, 8, 13),
            warnings=warnings,
        )

        self.assertEqual(overview["weeklyAddition"]["total"], 0)
        self.assertEqual(overview["weeklyAddition"]["invalidCreatedTimeCount"], 1)
        self.assertEqual(
            overview["weeklyAddition"]["invalidCreatedTimeProjects"],
            [{"code": "TDT-005", "name": "时间异常"}],
        )
        self.assertTrue(any("系统创建时间缺失或无法解析" in warning for warning in warnings))

    def test_record_created_time_scan_uses_official_query_records_api(self) -> None:
        first_page = {
            "ok": True,
            "data": {
                "items": [{"record_id": "rec-1", "created_time": "1786294800000"}],
                "has_more": True,
                "page_token": "next-page",
            },
        }
        second_page = {
            "ok": True,
            "data": {
                "items": [{"record_id": "rec-2", "created_time": "1786381200000"}],
                "has_more": False,
            },
        }
        completed = [
            SimpleNamespace(returncode=0, stdout=json.dumps(first_page), stderr=""),
            SimpleNamespace(returncode=0, stdout=json.dumps(second_page), stderr=""),
        ]

        with mock.patch.object(gd.subprocess, "run", side_effect=completed) as run:
            result = gd.scan_record_created_times(
                base_token="base-token",
                table_id="tblMain",
                primary_field_name="TDT/子任务名称",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                logs=[],
            )

        self.assertEqual(result, {
            "rec-1": "1786294800000",
            "rec-2": "1786381200000",
        })
        first_command = run.call_args_list[0].args[0]
        self.assertEqual(first_command[1:4], ["api", "POST", "/open-apis/bitable/v1/apps/base-token/tables/tblMain/records/search"])
        first_body = json.loads(first_command[first_command.index("--data") + 1])
        self.assertEqual(first_body, {
            "automatic_fields": True,
            "field_names": ["TDT/子任务名称"],
        })
        second_params = json.loads(run.call_args_list[1].args[0][run.call_args_list[1].args[0].index("--params") + 1])
        self.assertEqual(second_params["page_token"], "next-page")

    def test_development_achievement_uses_project_status_rules(self) -> None:
        completed_statuses = (
            "已完成",
            "开发完成_正常",
            "开发完成_顺延",
            "开发完成_变更",
            "开发完成_风险",
            "开发完成_技术不可行",
            "开发完成_价值fail",
            "开发完成_进度fail",
        )
        records = [
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: status}
            for status in completed_statuses
        ] + [
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: "进行中", gd.RISK_STATUS_FIELD: "中风险"},
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: "开发中_延期"},
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: "待确认_FAIL", gd.RISK_STATUS_FIELD: "高风险"},
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: "开发完成_延期fail"},
            {"TDT/子任务": "子任务", gd.PROJECT_STATUS_FIELD: "开发完成_未列入状态fail"},
        ]

        summary = gd.build_development_summary(records, [])

        self.assertEqual(summary["completedStatuses"], list(completed_statuses))
        self.assertEqual(summary["statusCounts"], {
            "inDevelopment": 1,
            "completed": 8,
            "paused": 0,
            "canceled": 0,
            "rejected": 0,
            "unclassified": 4,
        })
        self.assertEqual(summary["riskCounts"], {"medium": 1, "high": 1, "delayed": 2, "fail": 5})
        self.assertEqual(summary["formulaNumerator"], 9)
        self.assertEqual(summary["formulaDenominator"], 9)
        self.assertEqual(summary["achievementRate"], 0.0)

    def test_issue_table_preserves_nonempty_base_values(self) -> None:
        row = ["/", "未填写", "—", "暂无", "", "/", "-", "／", "--", "无", "/", "30"]
        payload = {"data": {"fields": gd.ISSUE_FIELDS, "data": [row], "has_more": False}}
        with (
            mock.patch.object(gd, "parse_base_link", return_value=("token", "table", "view")),
            mock.patch.object(gd, "get_view_name", return_value="问题视图"),
            mock.patch.object(gd, "run_lark_record_list", return_value=payload),
        ):
            result = gd.build_issue_data(
                issue_base_url="https://example.invalid/base/token?table=table&view=view",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                run_date=dt.date(2026, 7, 22),
                logs=[],
                warnings=[],
            )
        items = [item for group in result["groups"] for item in group["items"]]
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0],
            {
                "item": "/",
                "taskName": "未填写",
                "task": "—",
                "progress": "暂无",
                "plannedDate": "",
                "adjustedDate": "/",
                "actualDate": "-",
                "proposer": "／",
                "department": "--",
                "owner": "无",
                "status": "/",
            },
        )

    def test_issue_weeks_use_runtime_iso_anchor_and_ignore_older_content(self) -> None:
        def row(**values: object) -> list[object]:
            return [values.get(field, "") for field in gd.ISSUE_FIELDS]

        payload = {
            "data": {
                "fields": gd.ISSUE_FIELDS,
                "data": [
                    row(Week=31),
                    row(Week=30),
                    row(Week=29, Item="I-29", 任务="不应进入当前看板"),
                ],
                "has_more": False,
            }
        }
        with (
            mock.patch.object(gd, "parse_base_link", return_value=("token", "table", "view")),
            mock.patch.object(gd, "get_view_name", return_value="问题视图"),
            mock.patch.object(gd, "run_lark_record_list", return_value=payload),
        ):
            result = gd.build_issue_data(
                issue_base_url="https://example.invalid/base/token?table=table&view=view",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                run_date=dt.date(2026, 8, 1),
                logs=[],
                warnings=[],
            )

        self.assertEqual(result["week"], 31)
        self.assertEqual(result["previousWeek"], 30)
        self.assertEqual(result["weekLabel"], "第30周—第31周")
        self.assertEqual([group["week"] for group in result["groups"]], [30, 31])
        self.assertEqual(result["total"], 0)

    def test_issue_week_anchor_uses_date_subtraction_across_iso_year(self) -> None:
        def row(**values: object) -> list[object]:
            return [values.get(field, "") for field in gd.ISSUE_FIELDS]

        payload = {
            "data": {
                "fields": gd.ISSUE_FIELDS,
                "data": [
                    row(Week=53, Item="I-53", 任务="上周问题"),
                    row(Week=1, Item="I-01", 任务="本周问题"),
                ],
                "has_more": False,
            }
        }
        with (
            mock.patch.object(gd, "parse_base_link", return_value=("token", "table", "view")),
            mock.patch.object(gd, "get_view_name", return_value="问题视图"),
            mock.patch.object(gd, "run_lark_record_list", return_value=payload),
        ):
            result = gd.build_issue_data(
                issue_base_url="https://example.invalid/base/token?table=table&view=view",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                run_date=dt.date(2027, 1, 4),
                logs=[],
                warnings=[],
            )

        self.assertEqual(result["previousWeek"], 53)
        self.assertEqual(result["week"], 1)
        self.assertEqual(result["weekLabel"], "2026年第53周—2027年第1周")
        self.assertEqual(result["previousTotal"], 1)
        self.assertEqual(result["currentTotal"], 1)

    def test_innovation_table_preserves_nonempty_base_values(self) -> None:
        field_payload = {
            "data": {
                "fields": [
                    {"name": name, "id": f"field-{index}"}
                    for index, name in enumerate(gd.INNOVATION_FIELDS)
                ]
            }
        }
        record_payload = {
            "data": {
                "fields": list(gd.INNOVATION_FIELDS),
                "data": [["未填写", "/", "—", "暂无", "无"]],
                "has_more": False,
            }
        }
        with (
            mock.patch.object(gd, "parse_base_link", return_value=("token", "table", "view")),
            mock.patch.object(gd, "get_view_name", return_value="创新视图"),
            mock.patch.object(gd, "run_lark_field_list", return_value=field_payload),
            mock.patch.object(gd, "run_lark_record_list", return_value=record_payload),
        ):
            result = gd.build_innovation_competition(
                innovation_base_url="https://example.invalid/base/token?table=table&view=view",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                logs=[],
                warnings=[],
            )
        self.assertEqual(
            result["projects"],
            [{"name": "未填写", "track": "/", "stage": "—", "status": "暂无", "risk": "无"}],
        )


class DashboardConfigTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, payload: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_formal_config_only_returns_unique_pm_roster(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            path = self.write_json(directory, "dashboard_config.json", {"pm_roster": [" 甲 ", "乙"]})
            self.assertEqual(gd.load_dashboard_config(path), ["甲", "乙"])

    def test_formal_config_rejects_demo_fields_and_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            legacy = self.write_json(
                directory,
                "legacy.json",
                {"pm_roster": ["甲"], "tdts": [{"tdt": "Demo", "tasks": ["任务"]}]},
            )
            duplicate = self.write_json(directory, "duplicate.json", {"pm_roster": ["甲", "甲"]})
            with self.assertRaisesRegex(gd.SkillError, "未支持字段"):
                gd.load_dashboard_config(legacy)
            with self.assertRaisesRegex(gd.SkillError, "重复姓名"):
                gd.load_dashboard_config(duplicate)

    def test_legacy_scope_remains_separate(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            path = self.write_json(
                directory,
                "demo_scope.json",
                {"tdts": [{"tdt": "Demo", "tasks": ["任务"]}]},
            )
            self.assertEqual(gd.load_scope_file(path)["tdts"][0]["tdt"], "Demo")

    def test_formal_meeting_content_is_data_driven(self) -> None:
        content = gd.load_meeting_discipline(SRC_DIR / "meeting_content.json")
        self.assertTrue(content["enabled"])
        self.assertEqual([section["title"] for section in content["sections"]], [
            "会议纪律",
            "会议纪律--水果基金",
        ])
        self.assertEqual([len(section["items"]) for section in content["sections"]], [2, 7])


class DashboardYearTests(unittest.TestCase):
    def test_dashboard_year_uses_calendar_year_not_iso_week_year(self) -> None:
        with (
            mock.patch.object(gd, "get_view_name", return_value=gd.EXPECTED_VIEW_NAME),
            mock.patch.object(gd, "run_lark_field_list", return_value={"data": {"fields": []}}),
            mock.patch.object(gd, "scan_records", return_value=[]),
            mock.patch.object(gd, "match_field_tasks", return_value=[]),
            mock.patch.object(gd, "build_issue_data", return_value={}),
            mock.patch.object(gd, "build_innovation_competition", return_value={}),
        ):
            data = gd.build_data(
                base_url="https://example.invalid/base/token?table=table&view=view",
                lark_cli="lark-cli",
                as_identity="user",
                page_delay=0,
                scope=None,
                pm_roster=[],
                filter_field="是否上周三例会",
                filter_value="是",
                run_date=dt.date(2027, 1, 1),
                logs=[],
                warnings=[],
            )

        self.assertEqual(data["dashboardYear"], 2027)
        self.assertTrue(data["week"].startswith("2026 · W"))


class OfflineSnapshotFilenameTests(unittest.TestCase):
    def test_filename_uses_calendar_date_and_two_digit_iso_week(self) -> None:
        self.assertEqual(
            gd.offline_snapshot_filename(dt.date(2026, 7, 29)),
            "2026-07-29(W31)-TDT技术项目状态看板.html",
        )
        self.assertEqual(
            gd.offline_snapshot_filename(dt.date(2026, 1, 1)),
            "2026-01-01(W01)-TDT技术项目状态看板.html",
        )

    def test_realtime_snapshot_uses_shared_filename_rule(self) -> None:
        previous_state = dict(server.STATE)
        try:
            with tempfile.TemporaryDirectory() as raw_directory:
                directory = Path(raw_directory)
                template_path = directory / "template.html"
                template_path.write_text("<script>const DATA = /*__DATA__*/null;</script>", encoding="utf-8")
                server.STATE.update(
                    {
                        "cfg": SimpleNamespace(output_dir=directory, variant="legacy"),
                        "template_path": template_path,
                        "data": None,
                    }
                )

                output_path = server.write_offline_snapshot(
                    {"ok": True},
                    dt.date(2026, 7, 29),
                    generator=gd,
                )

                self.assertEqual(output_path.name, "2026-07-29(W31)-TDT技术项目状态看板.html")
                self.assertTrue(output_path.is_file())
                self.assertFalse(output_path.with_suffix(".html.tmp").exists())
        finally:
            server.STATE.clear()
            server.STATE.update(previous_state)


class StartupOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        server.STATE.update({"cfg": None, "template_path": None, "data": None})

    def run_main(self, events: list[str], fetch_side_effect: object = None) -> mock.Mock:
        class FakeServer:
            def __init__(self, address: tuple[str, int], handler: object) -> None:
                del address, handler
                events.append("bind")

            def serve_forever(self) -> None:
                events.append("serve")

        fetch_mock = mock.Mock(side_effect=fetch_side_effect)
        if fetch_side_effect is None:
            fetch_mock.return_value = {"groups": []}

        def record_fetch() -> dict:
            events.append("fetch")
            return fetch_mock()

        def record_replace(port: int) -> list[int]:
            del port
            events.append("replace")
            return []

        with tempfile.TemporaryDirectory() as raw_directory:
            config_path = self.write_config(Path(raw_directory))
            argv = [
                "serve_dashboard.py",
                "--base-url",
                "https://example.invalid/base/token?table=table&view=view",
                "--filter-field",
                "是否上周三例会",
                "--config",
                str(config_path),
                "--template",
                str(SRC_DIR / "template-dashboard-v1.3.0.html"),
                "--replace-existing",
                "--no-open",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(server, "fetch_data", side_effect=record_fetch),
                mock.patch.object(server, "replace_existing_dashboard", side_effect=record_replace),
                mock.patch.object(server, "DashboardHTTPServer", FakeServer),
            ):
                server.main()
        return fetch_mock

    @staticmethod
    def write_config(directory: Path) -> Path:
        path = directory / "dashboard_config.json"
        path.write_text('{"pm_roster":["甲"]}', encoding="utf-8")
        return path

    def test_initial_fetch_succeeds_before_old_service_is_replaced(self) -> None:
        events: list[str] = []
        self.run_main(events)
        self.assertEqual(events, ["fetch", "replace", "bind", "serve"])

    def test_initial_fetch_failure_preserves_old_service(self) -> None:
        events: list[str] = []
        with self.assertRaisesRegex(RuntimeError, "模拟抓取失败"):
            self.run_main(events, RuntimeError("模拟抓取失败"))
        self.assertEqual(events, ["fetch"])


if __name__ == "__main__":
    unittest.main()
