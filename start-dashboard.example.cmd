@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

REM TDT dashboard local server (template). Copy to start-dashboard.cmd and fill in real values.
REM start-dashboard.cmd is gitignored because it contains the real Base URL.

set "BASE_URL=<Formal progress and overview Base URL with table and view params>"
set "ISSUE_BASE_URL=<Formal issue Base URL with table and view params>"
set "INNOVATION_BASE_URL=<Formal innovation Base URL with table and view params>"
set "LARK_CLI=<path to lark-cli.cmd>"
set "CONFIG=%~dp0src\dashboard_config.json"
set "TEMPLATE=%~dp0src\template-dashboard-v1.3.0.html"
set "OUTPUT_DIR=%~dp0output"
set "VARIANT=v1.3.0"

if "%BASE_URL:~0,1%"=="<" (
  echo [提示] 这是占位模板，不能直接运行。
  echo 请把本文件复制为 start-dashboard.cmd，填入真实的 BASE_URL、ISSUE_BASE_URL、INNOVATION_BASE_URL 与 LARK_CLI 后再双击。
  echo start-dashboard.cmd 含真实 Base URL，已被 .gitignore 排除、不会入库。
  pause
  exit /b 1
)
if "%ISSUE_BASE_URL:~0,1%"=="<" (
  echo [提示] ISSUE_BASE_URL 仍是占位值，请填写后再双击。
  pause
  exit /b 1
)
if "%INNOVATION_BASE_URL:~0,1%"=="<" (
  echo [提示] INNOVATION_BASE_URL 仍是占位值，请填写后再双击。
  pause
  exit /b 1
)
if not exist "%CONFIG%" (
  echo [错误] 正式配置不存在：%CONFIG%
  echo 请复制 src\dashboard_config.example.json 为 src\dashboard_config.json 并填写 PM 顺序。
  pause
  exit /b 1
)

call "D:\ai-workspace\shared\scripts\python.cmd" "%~dp0src\serve_dashboard.py" --base-url "%BASE_URL%" --issue-base-url "%ISSUE_BASE_URL%" --innovation-base-url "%INNOVATION_BASE_URL%" --lark-cli "%LARK_CLI%" --config "%CONFIG%" --template "%TEMPLATE%" --output-dir "%OUTPUT_DIR%" --variant "%VARIANT%" --filter-field "是否上周三例会" --auto-port --replace-existing %*
pause
