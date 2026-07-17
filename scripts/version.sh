#!/usr/bin/env bash
# Read the current git tag, fallback to a default version.
# Usage: scripts/version.sh
# Output: a semver string (e.g. "0.1.0", "0.1.0-dev.abc1234")

set -euo pipefail

# Try to get the latest tag reachable from HEAD
TAG=$(git describe --tags --abbrev=0 2>/dev/null || true)

if [ -n "$TAG" ]; then
  # Strip leading 'v' if present
  echo "${TAG#v}"
else
  # Fallback: read from package.json
  if [ -f electron/package.json ]; then
    node -p "require('./electron/package.json').version"
  else
    echo "0.0.0-unknown"
  fi
fi
