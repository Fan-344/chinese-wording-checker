# -*- coding: utf-8 -*-
"""中國用語檢查工具 — Excel 報告輸出層（規格書第 6 節）。

報告存於「檢查報告/」資料夾，檔名：原檔名_檢查報告_YYYYMMDD_HHMMSS.xlsx。
含兩個工作表：
1. 總覽：受檢檔名、檢查時間、詞庫檔名與最後修改時間、詞庫規則數、
   檢查等級設定、結果統計。
2. 明細：位置、命中詞、修改建議、風險等級、前後文（命中詞以【】標示）、
   類別、備註；風險等級上色（高＝紅、中＝橘、低＝綠）、凍結首列、自動篩選。

不產生修正版檔案；絕不修改使用者的原始檔案。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from checker import CheckResult
from matcher import RISK_HIGH, RISK_LOW, RISK_MID

REPORT_DIR_NAME = "檢查報告"

# 風險等級底色：高＝紅、中＝橘、低＝綠。
_RISK_FILLS = {
    RISK_HIGH: PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
    RISK_MID: PatternFill(start_color="FFD8A8", end_color="FFD8A8", fill_type="solid"),
    RISK_LOW: PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
}
_RISK_FONTS = {
    RISK_HIGH: Font(color="9C0006"),
    RISK_MID: Font(color="974E00"),
    RISK_LOW: Font(color="006100"),
}

_DETAIL_HEADERS = ["位置", "命中詞", "修改建議", "風險等級", "前後文", "類別", "備註"]
_DETAIL_WIDTHS = [16, 12, 18, 10, 48, 12, 30]


def build_report_path(source_path: str, base_dir: str, now: Optional[datetime] = None) -> str:
    """組出報告檔路徑：base_dir/檢查報告/原檔名_檢查報告_YYYYMMDD_HHMMSS.xlsx"""
    now = now or datetime.now()
    stem = os.path.splitext(os.path.basename(source_path))[0]
    report_dir = os.path.join(base_dir, REPORT_DIR_NAME)
    os.makedirs(report_dir, exist_ok=True)
    filename = f"{stem}_檢查報告_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return os.path.join(report_dir, filename)


def write_report(
    report_path: str,
    source_path: str,
    result: CheckResult,
    lexicon_path: str,
    rule_count: int,
    lexicon_warnings: Optional[list] = None,
    now: Optional[datetime] = None,
) -> str:
    """寫出 Excel 檢查報告，回傳報告路徑。"""
    now = now or datetime.now()
    wb = Workbook()

    # ---- 工作表 1：總覽 ----
    ws = wb.active
    ws.title = "總覽"
    counts = result.hits_by_risk()
    lexicon_mtime = (
        datetime.fromtimestamp(os.path.getmtime(lexicon_path)).strftime("%Y-%m-%d %H:%M:%S")
        if os.path.exists(lexicon_path) else "（無法取得）"
    )
    level_text = "＋".join(
        lv for lv in (RISK_HIGH, RISK_MID, RISK_LOW) if lv in result.levels
    )
    overview_rows = [
        ("受檢檔名", os.path.basename(source_path)),
        ("檢查時間", now.strftime("%Y-%m-%d %H:%M:%S")),
        ("詞庫檔名", os.path.basename(lexicon_path)),
        ("詞庫最後修改時間", lexicon_mtime),
        ("詞庫規則數", rule_count),
        ("檢查等級設定", level_text),
        ("掃描單元數", result.total_units),
        ("通過數", result.passed_units),
        ("未通過數", result.failed_units),
        ("高風險命中數", counts.get(RISK_HIGH, 0)),
        ("中風險命中數", counts.get(RISK_MID, 0)),
        ("低風險命中數（僅供參考）", counts.get(RISK_LOW, 0)),
    ]
    for warning in (lexicon_warnings or []):
        overview_rows.append(("詞庫提醒", warning))

    bold = Font(bold=True)
    for r, (label, value) in enumerate(overview_rows, start=1):
        ws.cell(row=r, column=1, value=label).font = bold
        ws.cell(row=r, column=2, value=value)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 48

    # ---- 工作表 2：明細 ----
    ws2 = wb.create_sheet("明細")
    for c, header in enumerate(_DETAIL_HEADERS, start=1):
        cell = ws2.cell(row=1, column=c, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for c, width in enumerate(_DETAIL_WIDTHS, start=1):
        ws2.column_dimensions[chr(ord("A") + c - 1)].width = width

    for r, uh in enumerate(result.unit_hits, start=2):
        h = uh.hit
        ws2.cell(row=r, column=1, value=uh.position)
        ws2.cell(row=r, column=2, value=h.term)
        ws2.cell(row=r, column=3, value=h.suggestion)
        risk_cell = ws2.cell(row=r, column=4, value=h.risk)
        if h.risk in _RISK_FILLS:
            risk_cell.fill = _RISK_FILLS[h.risk]
            risk_cell.font = _RISK_FONTS[h.risk]
        ws2.cell(row=r, column=5, value=h.context)
        ws2.cell(row=r, column=6, value=h.category)
        ws2.cell(row=r, column=7, value=h.note)

    ws2.freeze_panes = "A2"  # 凍結首列
    last_row = max(2, len(result.unit_hits) + 1)
    ws2.auto_filter.ref = f"A1:G{last_row}"  # 自動篩選

    wb.save(report_path)
    return report_path
