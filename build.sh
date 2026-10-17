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

provenance="src/local_anonymizer/_build_provenance.py"
manifest="dist/LocalAnonymizer.manifest.json"
trap 'rm -f "$provenance"' EXIT HUP INT TERM
rm -f "$provenance"
uv run python scripts/build_provenance.py "$provenance"
.venv/bin/pyinstaller --noconfirm --clean LocalAnonymizer.spec
rm -f "$provenance"

if [ ! -f "$artifact" ]; then
  printf 'Build artifact is missing: %s\n' "$artifact" >&2
  exit 1
fi
if [ ! -x "$artifact" ]; then
  printf 'Build artifact is not executable: %s\n' "$artifact" >&2
  exit 1
fi

uv run python scripts/verify_packaged.py "$artifact" --write-manifest "$manifest"
trap - EXIT HUP INT TERM
printf 'Сборка: %s/%s\n' "$(pwd)" "$artifact"
