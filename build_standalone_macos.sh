#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/python-backend"
TAURI_DIR="$ROOT_DIR/src-tauri"
BIN_DIR="$TAURI_DIR/binaries"
PY_DIST_DIR="$BACKEND_DIR/dist/python-backend"
PY_BIN_NAME="python-backend"
PY_DIST_FILE="$BACKEND_DIR/dist/python-backend"

case "$(uname -m)" in
  arm64|aarch64)
    MAC_ARCH="aarch64"
    ;;
  x86_64)
    MAC_ARCH="x86_64"
    ;;
  *)
    echo "[错误] 不支持的 CPU 架构: $(uname -m)"
    exit 1
    ;;
esac

SIDECAR_NAME="python-backend-${MAC_ARCH}-apple-darwin"

log() {
  printf '%s\n' "$1"
}

ensure_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[错误] 找不到命令: $1"
    exit 1
  fi
}

clean_build_outputs() {
  log "[清理] 删除旧的构建产物..."
  rm -rf "$BACKEND_DIR/build" "$BACKEND_DIR/dist" "$TAURI_DIR/target"
  mkdir -p "$BIN_DIR"
  find "$BIN_DIR" -maxdepth 1 -type f -name 'python-backend-*-apple-darwin' -delete 2>/dev/null || true
  log "✅ 清理完成"
}

build_frontend() {
  log "[前端] 构建静态资源..."
  (cd "$ROOT_DIR" && npm run build:frontend)
}

build_python_backend() {
  log "[Python] 检查 PyInstaller..."
  export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-/tmp/a3agent-pyinstaller}"
  mkdir -p "$PYINSTALLER_CONFIG_DIR"
  if ! python3 -m PyInstaller --version >/dev/null 2>&1; then
    log "   未检测到 PyInstaller，开始安装依赖..."
    python3 -m pip install -r "$BACKEND_DIR/requirements.txt"
  fi

  log "[Python] 打包后端..."
  (cd "$BACKEND_DIR" && python3 -m PyInstaller headless_main.spec --clean)

  mkdir -p "$BIN_DIR"
  if [ -f "$PY_DIST_FILE" ]; then
    cp "$PY_DIST_FILE" "$BIN_DIR/$SIDECAR_NAME"
  elif [ -f "$PY_DIST_DIR/$PY_BIN_NAME" ]; then
    cp "$PY_DIST_DIR/$PY_BIN_NAME" "$BIN_DIR/$SIDECAR_NAME"
  else
    echo "[错误] 未找到打包后的 Python 后端: $PY_DIST_FILE 或 $PY_DIST_DIR/$PY_BIN_NAME"
    exit 1
  fi
  chmod +x "$BIN_DIR/$SIDECAR_NAME"
  log "✅ Python sidecar 已生成: $BIN_DIR/$SIDECAR_NAME"
}

build_tauri() {
  log "[Tauri] 开始构建 macOS 应用..."
  (cd "$ROOT_DIR" && npm run tauri build -- --bundles app)
}

build_dmg() {
  local app_bundle="$TAURI_DIR/target/release/bundle/macos/A3Agent.app"
  local dmg_dir="$TAURI_DIR/target/release/bundle/dmg"
  local dmg_path="$dmg_dir/A3Agent_0.1.0_${MAC_ARCH}.dmg"
  local dmg_script="$dmg_dir/bundle_dmg.sh"

  if [ ! -d "$app_bundle" ]; then
    echo "[错误] 未找到构建完成的 App: $app_bundle"
    exit 1
  fi

  if [ ! -x "$dmg_script" ]; then
    echo "[错误] 未找到 DMG 打包脚本: $dmg_script"
    exit 1
  fi

  log "[DMG] 生成安装镜像..."
  rm -f "$dmg_path"
  bash "$dmg_script" \
    --skip-jenkins \
    --volname "A3Agent" \
    "$dmg_path" \
    "$TAURI_DIR/target/release/bundle/macos"
}

print_summary() {
  log ""
  log "========================================"
  log "✅ macOS 打包完成"
  log "========================================"
  log "产物通常位于："
  log "  - App: src-tauri/target/release/bundle/macos/"
  log "  - DMG: src-tauri/target/release/bundle/dmg/"
  log "  - Tauri release: src-tauri/target/release/"
  log ""
  log "如果是 Apple Silicon，sidecar 名称为: python-backend-aarch64-apple-darwin"
  log "如果是 Intel，sidecar 名称为: python-backend-x86_64-apple-darwin"
}

log "========================================"
log "A3Agent macOS 打包脚本"
log "========================================"
log ""

ensure_cmd python3
ensure_cmd node
ensure_cmd npm
ensure_cmd cargo

if [ "${CLEAN:-1}" != "0" ]; then
  clean_build_outputs
  log ""
fi

build_frontend
log ""
build_python_backend
log ""
build_tauri
log ""
build_dmg
print_summary
