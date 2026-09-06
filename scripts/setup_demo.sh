#!/bin/zsh
# 光锥之内 · 任意 macOS 电脑一键安装 demo 依赖
# 用法：git clone 后在仓库根目录执行 ./scripts/setup_demo.sh
set -euo pipefail

project_dir="${0:A:h:h}"
cd "$project_dir"

print "==> 1/4 检查依赖"
command -v python3 >/dev/null || { print -u2 "需要 python3（建议 3.11+）"; exit 1; }
command -v node >/dev/null || { print -u2 "需要 Node.js（https://nodejs.org）"; exit 1; }
command -v curl >/dev/null || { print -u2 "需要 curl"; exit 1; }

print "==> 2/4 创建 Python 虚拟环境并安装后端依赖"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
  python3 -m venv "$project_dir/.venv"
fi
"$project_dir/.venv/bin/pip" install -q -r requirements.txt

print "==> 3/4 下载数据制品（约 48MB）"
mkdir -p artifacts
if [[ ! -f artifacts/catalog.sqlite ]]; then
  curl -L --fail -o /tmp/lightcone_artifacts.tar.gz \
    "https://github.com/DefyWish/Inside-the-light-cone/releases/download/demo-data-v1/artifacts_bundle.tar.gz"
  tar xzf /tmp/lightcone_artifacts.tar.gz -C "$project_dir"
else
  print "    数据制品已存在，跳过下载"
fi

print "==> 4/4 安装前端依赖"
cd "$project_dir/frontend"
npm install --silent

print ""
print "安装完成。启动前请配置模型 key（二选一）："
print "  A. 真机模式：在仓库根目录创建 .env，内容向团队索取（含 LIGHTCONE_PRIMARY/BACKUP 三件套）"
print "  B. Mock 模式：不配 .env 也能跑，自动使用保底重放"
print ""
print "启动：./scripts/run_demo.sh 然后打开 http://127.0.0.1:5173/"
