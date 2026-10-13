#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"

case "$(uname -s)" in
  Darwin)
    artifact="dist/LocalAnonymizer.app/Contents/MacOS/LocalAnonymizer"
    ;;
  Linux)
    artifact="dist/LocalAnonymizer/LocalAnonymizer"
    ;;
  *)
    printf 'Unsupported platform: %s\n' "$(uname -s)" >&2
    exit 1
    ;;
esac

if [ ! -x ".venv/bin/pyinstaller" ]; then
  printf '%s\n' 'Выполните: uv sync --extra dev --no-install-project' >&2
  exit 1
fi

.venv/bin/pyinstaller --noconfirm --clean LocalAnonymizer.spec

if [ ! -f "$artifact" ]; then
  printf 'Build artifact is missing: %s\n' "$artifact" >&2
  exit 1
fi
if [ ! -x "$artifact" ]; then
  printf 'Build artifact is not executable: %s\n' "$artifact" >&2
  exit 1
fi

printf 'Сборка: %s/%s\n' "$(pwd)" "$artifact"
