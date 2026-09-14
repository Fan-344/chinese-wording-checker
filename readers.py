# -*- coding: utf-8 -*-
"""中國用語檢查工具 — 檔案讀取層（規格書第 5 節）。

統一輸出為 [(位置字串, 文字)]：
- .txt：逐行，位置＝「第 N 行」
- .csv：逐格，位置＝「第 N 列第 M 欄」；自動嘗試 UTF-8（含 BOM）與 CP950
- .xlsx：逐工作表逐儲存格，位置＝「工作表名!A5」；僅讀取字串型儲存格，
  可選「指定欄位」（如 ["B", "D"]，留空＝全部檢查）

絕不修改使用者的原始檔案（僅以唯讀方式開啟）。
"""

from __future__ import annotations

import csv
import io
import os
from typing import List, Optional, Sequence, Tuple

Unit = Tuple[str, str]  # (位置字串, 文字)

SUPPORTED_EXTENSIONS = (".txt", ".csv", ".xlsx")


class FileReadError(Exception):
    """讀檔失敗時拋出，message 為可直接顯示給使用者的中文訊息。"""


def read_txt(path: str) -> List[Unit]:
    """逐行讀取，位置＝「第 N 行」。自動嘗試 UTF-8（含 BOM）與 CP950。

    只以「\\n」分行（相容 \\r\\n），不使用 splitlines()——
    後者會把孤立的 \\r、U+2028 等也當換行，導致行號與編輯器不一致。
    """
    data = _read_bytes(path)
    text = _decode(data, path)
    units: List[Unit] = []
    for i, line in enumerate(text.split("\n"), start=1):
        line = line.rstrip("\r")
        if line.strip():
            units.append((f"第 {i} 行", line))
    return units


def read_csv(path: str) -> List[Unit]:
    """逐格讀取，位置＝「第 N 列第 M 欄」。自動嘗試 UTF-8（含 BOM）與 CP950。"""
    data = _read_bytes(path)
    text = _decode(data, path)
    units: List[Unit] = []
    # 交給 csv 模組處理換行（含引號內換行的儲存格），列號＝邏輯 CSV 列。
    reader = csv.reader(io.StringIO(text))
    for r, row in enumerate(reader, start=1):
        for c, cell in enumerate(row, start=1):
            if cell.strip():
                units.append((f"第 {r} 列第 {c} 欄", cell))
    return units


def read_xlsx(path: str, columns: Optional[Sequence[str]] = None) -> List[Unit]:
    """逐工作表逐儲存格讀取，位置＝「工作表名!A5」。

    - 僅讀取字串型儲存格（數字、日期、公式結果非字串者跳過）。
    - columns：指定欄位字母（如 ["B", "D"]），留空或 None＝全部檢查。
    """
    try:
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover
        raise FileReadError("缺少 openpyxl 套件，無法讀取 Excel 檔案。") from e

    wanted = {c.strip().upper() for c in columns if c.strip()} if columns else None

    try:
        # read_only：不修改原始檔案；data_only：讀公式的快取結果而非公式字串。
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise FileReadError(
            f"無法開啟 Excel 檔案「{os.path.basename(path)}」，"
            "請確認檔案未損毀且非加密檔。"
        ) from e

    units: List[Unit] = []
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if not isinstance(cell.value, str) or not cell.value.strip():
                        continue
                    col_letter = get_column_letter(cell.column)
                    if wanted is not None and col_letter not in wanted:
                        continue
                    units.append((f"{ws.title}!{col_letter}{cell.row}", cell.value))
    finally:
        wb.close()
    return units


def read_file(path: str, columns: Optional[Sequence[str]] = None) -> List[Unit]:
    """依副檔名分派讀取。columns 僅對 .xlsx 生效。"""
    if not os.path.exists(path):
        raise FileReadError(f"找不到檔案：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return read_txt(path)
    if ext == ".csv":
        return read_csv(path)
    if ext == ".xlsx":
        return read_xlsx(path, columns=columns)
    raise FileReadError(
        f"不支援的檔案格式「{ext or '（無副檔名）'}」，"
        f"僅支援：{'、'.join(SUPPORTED_EXTENSIONS)}"
    )


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise FileReadError(f"無法讀取檔案「{os.path.basename(path)}」：{e}") from e


def _decode(data: bytes, path: str) -> str:
    """自動嘗試 UTF-8（含 BOM）與 CP950 編碼。"""
    for enc in ("utf-8-sig", "cp950"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileReadError(
        f"檔案「{os.path.basename(path)}」編碼無法辨識，"
        "請以 UTF-8 或 Big5（CP950）另存後重試。"
    )
