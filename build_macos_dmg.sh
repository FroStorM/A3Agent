#!/bin/bash
set -euo pipefail

APP_NAME="A3Agent"
VERSION_NAME="${1:-macos-$(date +%Y%m%d)}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
STANDALONE_DIR="${DIST_DIR}/standalone"
APP_DIR="${STANDALONE_DIR}/${APP_NAME}.app"
DMG_STAGING_DIR="${ROOT_DIR}/build/dmg-staging"
DMG_TEMP_PATH="${ROOT_DIR}/build/${APP_NAME}-${VERSION_NAME}-temp.dmg"
DMG_PATH="${DIST_DIR}/${APP_NAME}-${VERSION_NAME}.dmg"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App bundle not found: ${APP_DIR}" >&2
  echo "Build the standalone app first with ./build_macos_standalone_app.sh" >&2
  exit 1
fi

rm -rf "${DMG_STAGING_DIR}"
mkdir -p "${DMG_STAGING_DIR}"
cp -R "${APP_DIR}" "${DMG_STAGING_DIR}/"
ln -s /Applications "${DMG_STAGING_DIR}/Applications"

rm -f "${DMG_TEMP_PATH}" "${DMG_PATH}"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${DMG_STAGING_DIR}" \
  -ov \
  -format UDRW \
  "${DMG_TEMP_PATH}" >/dev/null

hdiutil convert "${DMG_TEMP_PATH}" \
  -ov \
  -format UDZO \
  -o "${DMG_PATH}" >/dev/null

rm -rf "${DMG_STAGING_DIR}"
rm -f "${DMG_TEMP_PATH}"

echo "${DMG_PATH}"
