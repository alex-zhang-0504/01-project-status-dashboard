#!/usr/bin/env python3
"""Local dashboard server with on-demand Base refresh.

Serves the dashboard template at http://127.0.0.1:<port>/ and re-fetches the
Feishu Base sources on every GET /api/data, so the in-page "重新生成" button
pulls the latest progress, issue, and innovation content. Changed data logic
is loaded transactionally from generate_dashboard.py before each refresh.

GET /          -> template HTML with the latest fetched DATA baked in
GET /api/data  -> fresh DATA JSON and an updated offline HTML snapshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import types
import webbrowser
from collections.abc import Callable, Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_dashboard as gd  # noqa: E402

PLACEHOLDER = "/*__DATA__*/null"
PROJECT_ID = "tdt-project-status-dashboard"
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PORTS = range(8710, 8720)


def calculate_build_id(project_dir: Path = PROJECT_DIR) -> str:
    runtime_files = (
        project_dir / "src" / "serve_dashboard.py",
        project_dir / "src" / "generate_dashboard.py",
        project_dir / "src" / "template-dashboard-v1.3.0.html",
        project_dir / "src" / "meeting_content.json",
    )
    digest = hashlib.sha256()
    for path in runtime_files:
        digest.update(path.relative_to(project_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


BUILD_ID = calculate_build_id()


def inspect_local_service(port: int) -> str:
    with socket.socket() as client:
        client.settimeout(0.25)
        if client.connect_ex(("127.0.0.1", port)) != 0:
            return "free"
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        return "occupied"
    is_current = (
        payload.get("project_id") == PROJECT_ID
        and payload.get("build_id") == BUILD_ID
    )
    return "current" if is_current else "occupied"


def choose_service_port(
    ports: Iterable[int] = DEFAULT_PORTS,
    inspect: Callable[[int], str] = inspect_local_service,
) -> tuple[str, int]:
    first_free: int | None = None
    for port in ports:
        state = inspect(port)
        if state == "current":
            return "reuse", port
        if state == "free" and first_free is None:
            first_free = port
    if first_free is None:
        raise gd.SkillError("本地端口8710至8719均被占用，无法启动项目状态看板")
    return "launch", first_free


def browser_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/?build={BUILD_ID}"

# 运行期配置、模板路径与最近一次数据（单用户本地使用，无并发要求）
STATE: dict = {"cfg": None, "template_path": None, "data": None}
FETCH_LOCK = threading.Lock()
GENERATOR_PATH = Path(gd.__file__).resolve()


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def generator_source_signature() -> tuple[int, int]:
    """用高精度修改时间和文件大小识别生成模块是否变化。"""
    stat = GENERATOR_PATH.stat()
    return stat.st_mtime_ns, stat.st_size


GENERATOR_SIGNATURE = generator_source_signature()


def load_generator_candidate() -> types.ModuleType:
    """直接编译源文件到隔离模块，成功前不影响当前运行版本。"""
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    code = compile(source, str(GENERATOR_PATH), "exec")
    candidate = types.ModuleType(gd.__name__)
    candidate.__file__ = str(GENERATOR_PATH)
    candidate.__package__ = gd.__package__
    candidate.__loader__ = gd.__loader__
    candidate.__spec__ = gd.__spec__
    exec(code, candidate.__dict__)
    required = ("build_data", "inject_template", "offline_snapshot_filename", "SkillError")
    missing = [name for name in required if not callable(getattr(candidate, name, None))]
    if missing:
        raise RuntimeError(f"生成模块缺少服务所需接口：{', '.join(missing)}")
    return candidate


def prepare_generator() -> tuple[types.ModuleType, tuple[int, int], bool]:
    """文件变化时准备候选模块；失败时保持当前模块和签名不变。"""
    signature = generator_source_signature()
    if signature == GENERATOR_SIGNATURE:
        return gd, signature, False
    try:
        candidate = load_generator_candidate()
        if generator_source_signature() != signature:
            raise RuntimeError("生成模块在热更新读取期间再次发生变化，请重试")
    except Exception as error:
        raise RuntimeError(
            "解析代码热更新失败，已保留当前运行版本和上次成功数据，"
            "且未覆盖离线看板；请修正 generate_dashboard.py 后重试，"
            "或重启 start-dashboard.cmd 检查当前代码能否正常启动："
            f"{type(error).__name__}: {error}"
        ) from error
    return candidate, signature, True


def fetch_data() -> dict:
    global gd, GENERATOR_SIGNATURE
    cfg = STATE["cfg"]
    logs: list[str] = []
    warnings: list[str] = []
    run_date = dt.date.today()
    with FETCH_LOCK:
        generator, signature, changed = prepare_generator()
        try:
            data = generator.build_data(
                base_url=cfg.base_url,
                lark_cli=cfg.lark_cli,
                as_identity=cfg.as_identity,
                page_delay=cfg.page_delay,
                scope=cfg.scope,
                pm_roster=cfg.pm_roster,
                filter_field=cfg.filter_field,
                filter_value=cfg.filter_value,
                run_date=run_date,
                logs=logs,
                warnings=warnings,
                issue_base_url=cfg.issue_base_url,
                innovation_base_url=cfg.innovation_base_url,
                meeting_discipline=cfg.meeting_discipline,
            )
            snapshot_path = write_offline_snapshot(data, run_date, generator=generator)
        except Exception as error:
            if changed:
                raise RuntimeError(
                    "解析代码热更新后的首次刷新失败，已继续使用旧运行版本和上次成功数据，"
                    "且未覆盖离线看板；请修正 generate_dashboard.py 后重试，"
                    "或重启 start-dashboard.cmd 检查当前代码能否正常启动："
                    f"{type(error).__name__}: {error}"
                ) from error
            raise
        if changed:
            gd = generator
            sys.modules[generator.__name__] = generator
            GENERATOR_SIGNATURE = signature
            print(f"解析代码热更新已生效：{GENERATOR_PATH}")
    for item in warnings:
        print(f"  警告：{item}")
    print(f"离线看板已更新：{snapshot_path}")
    return data


def load_template() -> str:
    """每次首页请求重新读取模板，避免本地开发期间继续展示旧页面。"""
    template_path = STATE["template_path"]
    template = template_path.read_text(encoding="utf-8")
    placeholder_count = template.count(PLACEHOLDER)
    if placeholder_count != 1:
        raise gd.SkillError(
            f"模板必须且只能包含一个数据占位符 {PLACEHOLDER}："
            f"{template_path}（实际 {placeholder_count} 个）"
        )
    return template


def write_offline_snapshot(
    data: dict,
    run_date: dt.date | None = None,
    *,
    generator: types.ModuleType | None = None,
) -> Path:
    """将当前数据写入可直接转发的单文件 HTML；同日生成覆盖同一文件。"""
    cfg = STATE["cfg"]
    generator = generator or gd
    snapshot_date = run_date or dt.date.today()
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / generator.offline_snapshot_filename(snapshot_date)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(generator.inject_template(STATE["template_path"], data), encoding="utf-8")
    os.replace(temporary_path, output_path)
    return output_path


def replace_existing_dashboard(port: int) -> list[int]:
    """Windows 下只替换同项目、同端口的旧看板服务，避免加载旧代码。"""
    if sys.platform != "win32":
        return []

    task_env = os.environ.copy()
    task_env["TDT_DASHBOARD_PORT"] = str(port)
    task_env["TDT_DASHBOARD_SCRIPT"] = str(Path(__file__).resolve())
    task_env["TDT_DASHBOARD_CURRENT_PID"] = str(os.getpid())
    command = r"""
$ErrorActionPreference = "Stop"
$portNumber = [int]$env:TDT_DASHBOARD_PORT
$scriptPath = $env:TDT_DASHBOARD_SCRIPT
$currentPid = [int]$env:TDT_DASHBOARD_CURRENT_PID
$connections = @(Get-NetTCPConnection -State Listen -LocalPort $portNumber -ErrorAction SilentlyContinue)
foreach ($servicePid in @($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
  if ($servicePid -eq $currentPid) { continue }
  $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $servicePid) -ErrorAction SilentlyContinue
  if ($null -eq $process -or $null -eq $process.CommandLine) { continue }
  if ($process.CommandLine.IndexOf($scriptPath, [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
  $parent = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $process.ParentProcessId) -ErrorAction SilentlyContinue
  Stop-Process -Id $servicePid -Force -ErrorAction Stop
  if ($null -ne $parent -and $parent.Name -eq "cmd.exe" -and $null -ne $parent.CommandLine -and $parent.CommandLine -like "*start-dashboard.cmd*") {
    Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Write-Output $servicePid
}
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=task_env,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "未知错误").strip()
        raise gd.SkillError(f"替换旧看板服务失败：{detail}")
    stopped = [int(value) for value in proc.stdout.split() if value.isdigit()]
    if stopped:
        print("已停止旧看板服务：" + "、".join(str(value) for value in stopped))
    return stopped


class Handler(BaseHTTPRequestHandler):
    server_version = "TDTDashboard/1.2.0"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print(f"[{dt.datetime.now():%H:%M:%S}] 客户端在响应完成前断开连接，服务继续运行")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            payload = json.dumps(STATE["data"], ensure_ascii=False).replace("</", "<\\/")
            html = load_template().replace(PLACEHOLDER, payload)
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
        elif path == "/api/data":
            try:
                data = fetch_data()
                STATE["data"] = data
                self._send(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))
            except Exception as error:  # 刷新失败返回 500，前端提示并回退旧数据
                print(f"刷新失败：{type(error).__name__}: {error}", file=sys.stderr)
                body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", body)
        elif path == "/api/health":
            body = json.dumps(
                {"status": "ok", "project_id": PROJECT_ID, "build_id": BUILD_ID}
            ).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{dt.datetime.now():%H:%M:%S}] {self.address_string()} {fmt % args}")


def main() -> int:
    src_dir = Path(__file__).resolve().parent
    project_dir = src_dir.parent

    port_was_explicit = "--port" in sys.argv[1:]
    parser = argparse.ArgumentParser(description="Serve TDT dashboard with on-demand Base refresh")
    parser.add_argument("--base-url", required=True, help="Base URL with table and view query params")
    parser.add_argument("--issue-base-url", default=None, help="Optional issue-list Base URL with table and view query params")
    parser.add_argument("--innovation-base-url", default=None, help="Optional innovation-project Base URL with table and view query params")
    parser.add_argument("--lark-cli", default="lark-cli", help="Path/name of lark-cli executable")
    parser.add_argument("--as", dest="as_identity", default="user", choices=["user", "bot"], help="lark-cli identity")
    parser.add_argument("--page-delay", type=float, default=0.2, help="Seconds between Base record-list pages")
    parser.add_argument("--config", default=str(src_dir / "dashboard_config.json"), help="Formal dashboard config JSON path")
    parser.add_argument("--scope", default=None, help="Legacy whitelist JSON path; required only without --filter-field")
    parser.add_argument(
        "--meeting-discipline",
        default=str(src_dir / "meeting_content.json"),
        help="Meeting-content JSON path",
    )
    parser.add_argument("--filter-field", default=None, help="按字段筛选收录子任务（替代白名单），如：是否上周三例会")
    parser.add_argument("--filter-value", default="是", help="筛选字段的命中值，默认「是」")
    parser.add_argument("--template", default=str(src_dir / "template-dashboard-v1.3.0.html"), help="Template HTML path")
    parser.add_argument("--output-dir", default=str(project_dir / "output"), help="Offline HTML output directory")
    parser.add_argument("--variant", default="v1.3.0", help="Legacy compatibility option; formal offline filename is fixed")
    parser.add_argument("--port", type=int, default=8710, help="Local port, default 8710")
    parser.add_argument("--auto-port", action="store_true", help="Reuse this build or select a free project-01 port")
    parser.add_argument("--replace-existing", action="store_true", help="Replace an existing dashboard process from this project on the selected port")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the browser")
    args = parser.parse_args()

    if args.auto_port and not port_was_explicit:
        action, args.port = choose_service_port()
        if action == "reuse":
            url = f"http://127.0.0.1:{args.port}/"
            print(f"当前版本看板已运行：{url}")
            if not args.no_open:
                webbrowser.open(browser_url(args.port))
            return 0

    template_path = Path(args.template).resolve()

    args.pm_roster = gd.load_dashboard_config(Path(args.config))
    args.scope = gd.load_scope_file(Path(args.scope)) if args.scope else None
    if not args.filter_field and args.scope is None:
        raise gd.SkillError("未设置 --filter-field 时必须同时传入旧白名单 --scope")
    args.meeting_discipline = gd.load_meeting_discipline(Path(args.meeting_discipline))
    STATE["cfg"] = args
    STATE["template_path"] = template_path
    load_template()

    print("启动前先拉取一次总表数据…")
    STATE["data"] = fetch_data()

    if args.replace_existing:
        replace_existing_dashboard(args.port)

    try:
        server = DashboardHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        raise gd.SkillError(f"无法监听本地端口 {args.port}：{error}") from error
    url = f"http://127.0.0.1:{args.port}/"
    print(f"看板服务已启动：{url} （Ctrl+C 停止；页面内「重新生成」将实时重读三类 Base）")
    if not args.no_open:
        webbrowser.open(browser_url(args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except gd.SkillError as error:
        print(f"错误：{error}")
        raise SystemExit(1)
