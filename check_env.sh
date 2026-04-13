#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "A3Agent macOS 环境检查工具"
echo "========================================"
echo

all_passed=1

check_cmd() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "✅ $label"
  else
    echo "❌ $label"
    all_passed=0
  fi
}

echo "[1/6] 检查 Python..."
if command -v python3 >/dev/null 2>&1; then
  python3 --version
else
  echo "❌ 未找到 python3"
  all_passed=0
fi
echo

echo "[2/6] 检查 Python 依赖..."
if python3 -c "import fastapi, uvicorn, requests" >/dev/null 2>&1; then
  echo "✅ fastapi / uvicorn / requests 已安装"
else
  echo "❌ 缺少 fastapi / uvicorn / requests"
  echo "   可执行: python3 -m pip install -r python-backend/requirements.txt"
  all_passed=0
fi
echo

echo "[3/6] 检查 Node.js / npm..."
check_cmd "node 已安装" "node --version"
check_cmd "npm 已安装" "npm --version"
echo

echo "[4/6] 检查 Rust / Cargo..."
check_cmd "cargo 已安装" "cargo --version"
echo

echo "[5/6] 检查 Xcode 命令行工具..."
if xcode-select -p >/dev/null 2>&1; then
  echo "✅ Xcode Command Line Tools 已安装"
else
  echo "❌ 未安装 Xcode Command Line Tools"
  echo "   可执行: xcode-select --install"
  all_passed=0
fi
echo

echo "[6/6] 检查项目目录..."
if [ -f "python-backend/headless_main.py" ] && [ -f "src-tauri/tauri.conf.json" ]; then
  echo "✅ 项目目录结构正常"
else
  echo "❌ 项目目录结构异常，请在仓库根目录运行"
  all_passed=0
fi
echo

echo "========================================"
if [ "$all_passed" -eq 1 ]; then
  echo "✅ 环境检查通过"
  echo "========================================"
  echo "可以运行:"
  echo "  - 开发模式: npm run tauri dev"
  echo "  - macOS 打包: npm run build:mac"
else
  echo "❌ 环境检查失败"
  echo "========================================"
fi
