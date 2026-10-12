#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x ".venv/bin/pyinstaller" ]; then
  printf '%s\n' 'Выполните: uv sync --extra dev --no-install-project' >&2
  exit 1
fi
.venv/bin/pyinstaller --noconfirm --clean LocalAnonymizer.spec
printf '%s\n' "Сборка: $(pwd)/dist/LocalAnonymizer/LocalAnonymizer"
