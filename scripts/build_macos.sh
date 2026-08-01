#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "このビルドはmacOS上で実行してください。" >&2
    exit 1
fi

PYTHON_BIN="python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

# PyInstallerのキャッシュもプロジェクト内へ置き、環境差による権限問題を防ぎます。
export PYINSTALLER_CONFIG_DIR="$PROJECT_DIR/build/pyinstaller-cache"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean kakeibo.spec

echo
echo "ビルドが完了しました。"
echo "アプリ: $PROJECT_DIR/dist/かんたん家計簿.app"
echo "Finderでダブルクリックして起動できます。"
