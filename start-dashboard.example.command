#!/bin/bash
# TDT dashboard local server template (macOS). Copy to start-dashboard.command and fill in real values.
# start-dashboard.command is gitignored because it contains the real Base URL.
# First run on mac: chmod +x start-dashboard.command
cd "$(dirname "$0")"

BASE_URL='<Base URL with table and view params>'
ISSUE_BASE_URL='<Issue Base URL with table and view params>'
INNOVATION_BASE_URL='<Innovation Base URL with table and view params>'
LARK_CLI='lark-cli'
CONFIG='src/dashboard_config.json'
TEMPLATE='src/template-dashboard-v1.3.0.html'
OUTPUT_DIR='output'
VARIANT='v1.3.0'

if [[ "$BASE_URL" == '<'* ]]; then
  echo "[提示] 这是占位模板，不能直接运行。"
  echo "请把本文件复制为 start-dashboard.command，填入真实的 BASE_URL、ISSUE_BASE_URL 与 INNOVATION_BASE_URL 后再运行。"
  echo "start-dashboard.command 含真实 Base URL，已被 .gitignore 排除、不会入库。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi
if [[ "$ISSUE_BASE_URL" == '<'* ]]; then
  echo "[提示] ISSUE_BASE_URL 仍是占位值，请填写后再运行。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi
if [[ "$INNOVATION_BASE_URL" == '<'* ]]; then
  echo "[提示] INNOVATION_BASE_URL 仍是占位值，请填写后再运行。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "[错误] 正式配置不存在：$CONFIG"
  echo "请复制 src/dashboard_config.example.json 为 src/dashboard_config.json 并填写 PM 顺序。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi

python3 src/serve_dashboard.py --base-url "$BASE_URL" --issue-base-url "$ISSUE_BASE_URL" --innovation-base-url "$INNOVATION_BASE_URL" --lark-cli "$LARK_CLI" --config "$CONFIG" --template "$TEMPLATE" --output-dir "$OUTPUT_DIR" --variant "$VARIANT" --filter-field "是否上周三例会" --auto-port "$@"
read -r -p "服务已停止，按回车关闭窗口..."
