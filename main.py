# -*- coding: utf-8 -*-
"""中國用語檢查工具 — 終端機入口（Mac）。

用法：
  互動模式（雙擊 中國用語檢查.command 進入）：
      python3 main.py
      → 把檔案拖進終端機視窗後按 Enter 即可檢查，可一次拖多個檔案。

  指令模式：
      python3 main.py 檔案1.xlsx 檔案2.txt [--含低風險] [--不開啟報告]

詞庫 `中國用語對照資料庫.csv` 須與本程式位於同一資料夾。
報告輸出至同資料夾下的 `檢查報告/`，絕不修改原始檔案。
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

from checker import check_units
from matcher import ALL_LEVELS, DEFAULT_LEVELS, load_rules
from readers import SUPPORTED_EXTENSIONS, FileReadError, read_file
from report import build_report_path, write_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEXICON_PATH = os.path.join(BASE_DIR, "中國用語對照資料庫.csv")


def _print_header() -> None:
    print("=" * 46)
    print("  中國用語檢查工具")
    print("  支援格式：" + "、".join(SUPPORTED_EXTENSIONS))
    print("=" * 46)


def _load_lexicon():
    if not os.path.exists(LEXICON_PATH):
        print("【錯誤】找不到詞庫檔「中國用語對照資料庫.csv」。")
        print(f"請將詞庫 CSV 放在：{BASE_DIR}/")
        sys.exit(1)
    try:
        rules, warnings = load_rules(LEXICON_PATH)
    except ValueError as e:
        print(f"【錯誤】詞庫格式有問題：{e}")
        sys.exit(1)
    for w in warnings:
        print(f"【提醒】{w}")
    print(f"已載入詞庫：{len(rules)} 條規則\n")
    return rules, warnings


def _check_one(path: str, rules, warnings, levels) -> str | None:
    """檢查單一檔案，回傳報告路徑（失敗回傳 None）。"""
    name = os.path.basename(path)
    try:
        units = read_file(path)
    except FileReadError as e:
        print(f"✗ {name}：{e}")
        return None
    result = check_units(units, rules, levels=levels)
    report_path = build_report_path(path, BASE_DIR)
    write_report(
        report_path, path, result, LEXICON_PATH,
        rule_count=len(rules), lexicon_warnings=warnings,
    )
    status = "✅ 全數通過" if result.failed_units == 0 else "⚠️ 建議修改"
    print(f"{status}  {name}")
    print(f"    掃描 {result.total_units} 處，通過 {result.passed_units} 處，"
          f"發現 {result.total_hits} 處建議修改")
    print(f"    報告：{os.path.relpath(report_path, BASE_DIR)}")
    return report_path


def _open_reports(paths) -> None:
    for p in paths:
        subprocess.run(["open", p], check=False)


def _parse_dropped(line: str) -> list:
    """解析拖進終端機的檔案路徑（終端機會自動加上跳脫字元）。"""
    try:
        return [p for p in shlex.split(line) if p]
    except ValueError:
        return [line.strip()] if line.strip() else []


def run_interactive(rules, warnings, levels) -> None:
    print("把要檢查的檔案「拖進這個視窗」後按 Enter（可一次拖多個）。")
    print("直接按 Enter 或輸入 q 離開。\n")
    while True:
        try:
            line = input("檔案 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line.lower() == "q":
            break
        paths = _parse_dropped(line)
        reports = []
        print()
        for p in paths:
            r = _check_one(os.path.expanduser(p), rules, warnings, levels)
            if r:
                reports.append(r)
        if reports:
            ans = input("\n按 Enter 開啟報告，或輸入 n 略過 > ").strip().lower()
            if ans != "n":
                _open_reports(reports)
        print()
    print("已結束，視窗可直接關閉。")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    include_low = "--含低風險" in argv
    no_open = "--不開啟報告" in argv
    files = [a for a in argv if not a.startswith("--")]
    levels = set(ALL_LEVELS) if include_low else set(DEFAULT_LEVELS)

    _print_header()
    rules, warnings = _load_lexicon()
    if include_low:
        print("（本次含低風險參考詞）\n")

    if not files:
        run_interactive(rules, warnings, levels)
        return 0

    reports = []
    failed = False
    for p in files:
        r = _check_one(os.path.expanduser(p), rules, warnings, levels)
        if r:
            reports.append(r)
        else:
            failed = True
    if reports and not no_open:
        _open_reports(reports)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
