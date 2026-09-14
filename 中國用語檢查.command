#!/bin/bash
# 中國用語檢查工具 — 雙擊啟動（Mac）
# 首次執行會自動安裝所需套件（需要網路），之後離線可用。

cd "$(dirname "$0")" || exit 1

VENV=".venv"

if [ ! -x "$VENV/bin/python3" ]; then
    echo "首次執行，正在準備環境（約需一分鐘）…"
    python3 -m venv "$VENV" || { echo "【錯誤】無法建立 Python 環境，請聯絡 IT。"; read -r -p "按 Enter 關閉…"; exit 1; }
    "$VENV/bin/pip" install --quiet --disable-pip-version-check openpyxl || {
        echo "【錯誤】套件安裝失敗，請確認網路後重試。"
        rm -rf "$VENV"
        read -r -p "按 Enter 關閉…"
        exit 1
    }
    echo "環境準備完成。"
    echo
fi

"$VENV/bin/python3" main.py
read -r -p "按 Enter 關閉視窗…"
