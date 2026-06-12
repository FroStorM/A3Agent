#!/bin/bash
set -euo pipefail

APP_NAME="A3Agent"
VERSION_NAME="${1:-macos-light-$(date +%Y%m%d)}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_VENV_DIR="${ROOT_DIR}/.venv-mac-build-light"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements-macos-build-light.txt"
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
  echo "Python 3.12 is required to build the lightweight macOS release." >&2
  echo "Install it first or run: PYTHON_BIN=/path/to/python3.12 $0" >&2
  exit 1
fi

PY_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PY_VERSION}" != "3.12" ]]; then
  echo "Python 3.12 is required, got ${PY_VERSION} from ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -x "${BUILD_VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${BUILD_VENV_DIR}"
fi

"${BUILD_VENV_DIR}/bin/python" -m pip install -r "${REQUIREMENTS_FILE}"

A3AGENT_INCLUDE_DOCPACK=0 PYTHON_BIN="${BUILD_VENV_DIR}/bin/python" "${ROOT_DIR}/build_macos_standalone_app.sh" "${VERSION_NAME}"
"${ROOT_DIR}/build_macos_dmg.sh" "${VERSION_NAME}"

mkdir -p "${ROOT_DIR}/release"
cp -f "${ROOT_DIR}/dist/${APP_NAME}-${VERSION_NAME}.zip" "${ROOT_DIR}/release/"
cp -f "${ROOT_DIR}/dist/${APP_NAME}-${VERSION_NAME}.dmg" "${ROOT_DIR}/release/"

echo "${ROOT_DIR}/release/${APP_NAME}-${VERSION_NAME}.zip"
echo "${ROOT_DIR}/release/${APP_NAME}-${VERSION_NAME}.dmg"
