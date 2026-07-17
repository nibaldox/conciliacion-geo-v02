#!/usr/bin/env bash
# Test scripts/version.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_SCRIPT="${SCRIPT_DIR}/version.sh"

cd "${SCRIPT_DIR}/.."

# Test 1: With a tag
git config user.email "test@example.com"
git config user.name "Test"
git commit -m "test" --allow-empty
git tag v0.5.0

VERSION=$(bash "$VERSION_SCRIPT")
if [ "$VERSION" != "0.5.0" ]; then
  echo "FAIL: expected 0.5.0, got $VERSION"
  exit 1
fi
echo "PASS: git tag version"

# Test 2: Without a tag, fallback to package.json
git tag -d v0.5.0
VERSION=$(bash "$VERSION_SCRIPT")
EXPECTED=$(node -p "require('./electron/package.json').version")
if [ "$VERSION" != "$EXPECTED" ]; then
  echo "FAIL: expected $EXPECTED, got $VERSION"
  exit 1
fi
echo "PASS: package.json fallback"

echo "All version tests pass"
