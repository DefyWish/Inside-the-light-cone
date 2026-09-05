#!/bin/zsh
set -euo pipefail

project_dir="${0:A:h:h}"
python_bin="$project_dir/envs/jialuo-tree/bin/python"

if [[ ! -x "$python_bin" ]]; then
  print -u2 "缺少项目环境：先按 README 创建 envs/jialuo-tree。"
  exit 1
fi

cleanup() {
  [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null || true
  [[ -n "$frontend_pid" ]] && kill "$frontend_pid" 2>/dev/null || true
}
backend_pid=""
frontend_pid=""
trap cleanup EXIT INT TERM

cd "$project_dir"
"$python_bin" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18765 &
backend_pid=$!

cd "$project_dir/frontend"
npm run dev -- --port 5173 &
frontend_pid=$!

print "光锥之内已启动：http://127.0.0.1:5173/"
wait "$backend_pid" "$frontend_pid"
