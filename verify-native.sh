#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

case "$(uname -s)" in
  Darwin)
    executable="dist/LocalAnonymizer.app/Contents/MacOS/LocalAnonymizer"
    ;;
  Linux)
    executable="dist/LocalAnonymizer/LocalAnonymizer"
    ;;
  *)
    echo "verify-native.sh supports Linux and macOS only" >&2
    exit 2
    ;;
esac

if [ ! -x "$executable" ]; then
  echo "Packaged executable not found: $executable" >&2
  echo "Run ./build.sh on this operating system first." >&2
  exit 2
fi

uv run python scripts/verify_packaged.py "$executable"

echo "Native package verification passed: $executable"
