#!/bin/bash
set -euo pipefail

APP_NAME="A3Agent"
VERSION_NAME="${1:-macos-$(date +%Y%m%d)}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
WORK_DIR="${ROOT_DIR}/build/pyinstaller"
SPEC_DIR="${ROOT_DIR}/build/pyinstaller"
STANDALONE_DIR="${DIST_DIR}/standalone"
ICON_PATH="${DIST_DIR}/A3Agent-standalone.icns"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in \
    /opt/homebrew/opt/python@3.12/bin/python3.12 \
    /usr/local/opt/python@3.12/bin/python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    python3.12
  do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${candidate}")"
      break
    fi
  done
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Python 3.12 is required. Install it or run: PYTHON_BIN=/path/to/python3.12 $0" >&2
  exit 1
fi

PY_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PY_VERSION}" != "3.12" ]]; then
  echo "Python 3.12 is required, got ${PY_VERSION} from ${PYTHON_BIN}" >&2
  exit 1
fi

mkdir -p "${DIST_DIR}" "${WORK_DIR}" "${SPEC_DIR}" "${STANDALONE_DIR}"
export PYINSTALLER_CONFIG_DIR="${WORK_DIR}/pyinstaller-cache"
mkdir -p "${PYINSTALLER_CONFIG_DIR}"

"${PYTHON_BIN}" - "${ROOT_DIR}/frontend/app_icon_round.png" "${ICON_PATH}" <<'PYICON'
import sys
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
img = Image.open(src)
if img.mode not in ("RGB", "RGBA"):
    img = img.convert("RGBA")
img.save(dst, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
PYICON

rm -rf "${STANDALONE_DIR}/${APP_NAME}.app"

PYINSTALLER_ARGS=(
  --noconfirm
  --clean
  --windowed
  --name "${APP_NAME}"
  --distpath "${STANDALONE_DIR}"
  --workpath "${WORK_DIR}"
  --specpath "${SPEC_DIR}"
  --icon "${ICON_PATH}"
  --add-data "${ROOT_DIR}/frontend:frontend"
  --add-data "${ROOT_DIR}/assets:assets"
  --add-data "${ROOT_DIR}/memory:memory"
  --add-data "${ROOT_DIR}/frontends:frontends"
  --add-data "${ROOT_DIR}/plugins:plugins"
  --add-data "${ROOT_DIR}/reflect:reflect"
  --add-data "${ROOT_DIR}/api_server.py:."
  --add-data "${ROOT_DIR}/agentmain.py:."
  --add-data "${ROOT_DIR}/agent_loop.py:."
  --add-data "${ROOT_DIR}/ga.py:."
  --add-data "${ROOT_DIR}/llmcore.py:."
  --add-data "${ROOT_DIR}/path_utils.py:."
  --add-data "${ROOT_DIR}/simphtml.py:."
  --hidden-import "uvicorn.loops.auto"
  --hidden-import "uvicorn.protocols.http.auto"
  --hidden-import "uvicorn.protocols.websockets.auto"
  --hidden-import "uvicorn.lifespan.on"
  --hidden-import "anyio._backends._asyncio"
  --hidden-import "objc"
  --hidden-import "Cocoa"
  --hidden-import "Foundation"
  --hidden-import "WebKit"
  --hidden-import "PyObjCTools"
  --hidden-import "tkinter"
  --hidden-import "_tkinter"
  --hidden-import "sqlite3"
  --hidden-import "_sqlite3"
  --hidden-import "PIL.ImageTk"
  --hidden-import "PIL.ImageSequence"
  --hidden-import "reflect.autonomous"
  --hidden-import "reflect.scheduler"
)

if [[ "${A3AGENT_INCLUDE_DOCPACK:-0}" == "1" ]]; then
  PYINSTALLER_ARGS+=(
    --hidden-import "fitz"
    --hidden-import "pypdf"
    --hidden-import "pdfplumber"
    --hidden-import "pdfminer"
    --hidden-import "pypdfium2"
    --hidden-import "docx"
    --hidden-import "openpyxl"
    --hidden-import "pptx"
    --hidden-import "pandas"
    --hidden-import "lxml"
    --hidden-import "cv2"
    --hidden-import "yaml"
    --hidden-import "markdownify"
    --hidden-import "chardet"
    --hidden-import "rank_bm25"
    --hidden-import "striprtf"
    --hidden-import "ebooklib"
  )
fi

"${PYTHON_BIN}" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "${ROOT_DIR}/launch_app.py"

APP_DIR="${STANDALONE_DIR}/${APP_NAME}.app"

find "${APP_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${APP_DIR}" -name '*.pyc' -delete
find "${APP_DIR}" -name '.DS_Store' -delete

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || true
fi

rm -f "${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.zip"
(
  cd "${STANDALONE_DIR}"
  zip -qry "${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.zip" "${APP_NAME}.app" \
    -x '*/__pycache__/*' '*.pyc' '*/.DS_Store'
)

echo "${APP_DIR}"
echo "${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.zip"
