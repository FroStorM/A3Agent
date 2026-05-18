#!/bin/bash
set -euo pipefail

APP_NAME="A3Agent"
VERSION_NAME="${1:-dev-20260507}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_DIR="${DIST_DIR}/${APP_NAME}.app"
RES_DIR="${APP_DIR}/Contents/Resources"
MACOS_DIR="${APP_DIR}/Contents/MacOS"

rm -rf "${APP_DIR}"
mkdir -p "${RES_DIR}" "${MACOS_DIR}"

rsync -a \
  --exclude '.git' \
  --exclude 'dist' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'temp' \
  "${ROOT_DIR}/" "${RES_DIR}/"

cat > "${MACOS_DIR}/${APP_NAME}" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")/../Resources" && pwd)"
cd "${APP_ROOT}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:/Library/Frameworks/Python.framework/Versions/3.11/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/Library/Frameworks/Python.framework/Versions/3.9/bin:/Library/Frameworks/Python.framework/Versions/3.7/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export GA_BASE_DIR="${APP_ROOT}"
export GA_APP_NAME="A3Agent"
export PYTHONUNBUFFERED=1

LOG_DIR="${HOME}/Library/Logs/A3Agent"
mkdir -p "${LOG_DIR}" 2>/dev/null || LOG_DIR="/tmp/A3Agent-logs"
mkdir -p "${LOG_DIR}" 2>/dev/null || LOG_DIR="/tmp"
LOG_FILE="${LOG_DIR}/launch.log"

PYTHON_BIN=""
for candidate in \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
  "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
  "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3" \
  "/Library/Frameworks/Python.framework/Versions/3.9/bin/python3" \
  "/Library/Frameworks/Python.framework/Versions/3.7/bin/python3" \
  "/usr/bin/python3"; do
  if [ -x "${candidate}" ]; then
    PYTHON_BIN="${candidate}"
    break
  fi
done

if [ -z "${PYTHON_BIN}" ]; then
  osascript -e 'display alert "A3Agent 启动失败" message "未找到 python3，请先安装 Python 3.10 或更高版本。"'
  exit 1
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') A3Agent launch ====="
  echo "APP_ROOT=${APP_ROOT}"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  "${PYTHON_BIN}" --version
  exec "${PYTHON_BIN}" "${APP_ROOT}/launch_app.py"
} >>"${LOG_FILE}" 2>&1
LAUNCHER
chmod +x "${MACOS_DIR}/${APP_NAME}"

cat > "${APP_DIR}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>cn.fudankw.a3agent</string>
  <key>CFBundleVersion</key>
  <string>${VERSION_NAME}</string>
  <key>CFBundleShortVersionString</key>
  <string>${VERSION_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

ICON_SRC="${ROOT_DIR}/frontend/app_icon_round.png"
if [ ! -f "${ICON_SRC}" ]; then
  ICON_SRC="${ROOT_DIR}/frontend/logo_square.png"
fi

if [ -f "${ICON_SRC}" ]; then
  if python3 - "${ICON_SRC}" "${APP_DIR}/Contents/Resources/AppIcon.icns" <<'PYICON'
import sys
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
img = Image.open(src)
if img.mode not in ("RGB", "RGBA"):
    img = img.convert("RGBA")
img.save(dst, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
PYICON
  then
    :
  elif command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET_DIR="${DIST_DIR}/AppIcon.iconset"
  rm -rf "${ICONSET_DIR}"
  mkdir -p "${ICONSET_DIR}"
  sips -z 16 16     "${ICON_SRC}" --out "${ICONSET_DIR}/icon_16x16.png" >/dev/null
  sips -z 32 32     "${ICON_SRC}" --out "${ICONSET_DIR}/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "${ICON_SRC}" --out "${ICONSET_DIR}/icon_32x32.png" >/dev/null
  sips -z 64 64     "${ICON_SRC}" --out "${ICONSET_DIR}/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "${ICON_SRC}" --out "${ICONSET_DIR}/icon_128x128.png" >/dev/null
  sips -z 256 256   "${ICON_SRC}" --out "${ICONSET_DIR}/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "${ICON_SRC}" --out "${ICONSET_DIR}/icon_256x256.png" >/dev/null
  sips -z 512 512   "${ICON_SRC}" --out "${ICONSET_DIR}/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "${ICON_SRC}" --out "${ICONSET_DIR}/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "${ICON_SRC}" --out "${ICONSET_DIR}/icon_512x512@2x.png" >/dev/null
  if ! iconutil -c icns "${ICONSET_DIR}" -o "${APP_DIR}/Contents/Resources/AppIcon.icns" >/dev/null 2>&1; then
    echo "Warning: iconutil failed; building app with the default macOS app icon." >&2
  fi
  rm -rf "${ICONSET_DIR}"
  else
    echo "Warning: failed to build app icon; using the default macOS app icon." >&2
  fi
fi

find "${APP_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${APP_DIR}" -name '*.pyc' -delete
find "${APP_DIR}" -name '.DS_Store' -delete

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || true
fi

rm -f "${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.zip"
(
  cd "${DIST_DIR}"
  zip -qry "${APP_NAME}-${VERSION_NAME}.zip" "${APP_NAME}.app" \
    -x '*/__pycache__/*' '*.pyc' '*/.DS_Store'
)

echo "${APP_DIR}"
echo "${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.zip"
