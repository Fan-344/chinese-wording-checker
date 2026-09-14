# -*- coding: utf-8 -*-
"""中國用語檢查工具 — 比對引擎（核心模組，可獨立測試）。

設計原則（規格書第 4 節）：
- 純函式：輸入一段文字 → 輸出命中清單。
- 最長詞優先：同一起點先比對長詞，命中後該區段不再以較短詞重複命中。
- 例外詞過濾：命中位置的上下文若構成任一例外詞則跳過（解決子字串誤判）。
- 僅比對「啟用＝是」的規則。
- 風險等級篩選：呼叫端可指定要檢查的等級集合，預設「高＋中」。

本模組不依賴 GUI / 檔案格式 / 報告輸出，可單獨用 unittest 驗證。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# 風險等級
RISK_HIGH = "高"
RISK_MID = "中"
RISK_LOW = "低"

# 預設檢查「高＋中」；「低」僅供參考，不影響通過判定（規格書第 4 節）。
DEFAULT_LEVELS: Set[str] = {RISK_HIGH, RISK_MID}
ALL_LEVELS: Set[str] = {RISK_HIGH, RISK_MID, RISK_LOW}

# 前後文擷取長度（各 18 字）。
CONTEXT_CHARS = 18

# 中國用語欄位內的「多詞替代」分隔符（例：賬號／賬戶）。
_TERM_SEPARATORS = ("／", "/")
# 例外詞分隔符（規格書以「;」分隔；同時容忍全形「；」）。
_EXCEPTION_SEPARATORS = (";", "；")

# 標準六欄詞庫升級為八欄時應填入的已知例外詞（規格書第 3 節）。
# 供讀取「舊版六欄 CSV」時作為安全網套用，避免子字串誤判。
KNOWN_EXCEPTIONS = {
    "生粉": ["花生粉", "花生醬"],
    "影院": ["電影院"],
    "線下": ["光線下"],
    "薯片": ["馬鈴薯片"],
    "黃瓜": ["小黃瓜", "大黃瓜"],
    "菠蘿": ["菠蘿油", "菠蘿包"],
    "就這": ["就這樣", "就這麼"],
    "程序": ["標準程序", "法律程序", "行政程序"],
}


@dataclass
class Rule:
    """單一偵測規則（中國用語欄若含「／」會拆成多筆共用同一建議）。"""

    term: str                       # 要偵測的詞
    suggestion: str                 # 建議替換詞（保留原欄位整串）
    risk: str                       # 高／中／低
    category: str = ""              # 類別
    note: str = ""                  # 備註
    exceptions: List[str] = field(default_factory=list)  # 例外詞
    enabled: bool = True            # 啟用＝是
    source_id: str = ""             # 對應詞庫編號

    def __post_init__(self) -> None:
        # 去除空白例外詞，維持穩定比對。
        self.exceptions = [e for e in self.exceptions if e]


@dataclass
class Hit:
    """一次命中結果。"""

    term: str          # 實際命中的詞
    suggestion: str    # 修改建議
    risk: str          # 風險等級
    start: int         # 起始位置（字元索引，0-based）
    context: str       # 前後文各 18 字，命中詞以【】標示
    end: int = 0       # 結束位置（不含）
    category: str = ""
    note: str = ""
    source_id: str = ""

    def as_tuple(self) -> Tuple[str, str, str, int, str]:
        """規格書第 4 節指定的核心輸出：(詞, 建議, 風險, 起始位置, 前後文)。"""
        return (self.term, self.suggestion, self.risk, self.start, self.context)


def _split_terms(raw: str) -> List[str]:
    """將『賬號／賬戶』拆為 ['賬號', '賬戶']。"""
    parts = [raw]
    for sep in _TERM_SEPARATORS:
        parts = [p for chunk in parts for p in chunk.split(sep)]
    return [p.strip() for p in parts if p.strip()]


def _split_exceptions(raw: str) -> List[str]:
    parts = [raw]
    for sep in _EXCEPTION_SEPARATORS:
        parts = [p for chunk in parts for p in chunk.split(sep)]
    return [p.strip() for p in parts if p.strip()]


def _is_excepted(text: str, pos: int, term: str, exceptions: Sequence[str]) -> bool:
    """判斷 text 中 [pos, pos+len(term)) 的命中是否落在某個例外詞內。

    對每個例外詞，找出 term 在例外詞中出現的每個位置 offset，
    再檢查 text 中對齊該 offset 的視窗是否等於整個例外詞。
    例：term=生粉、text=花生粉、exception=花生粉 → 命中被跳過。
    """
    for exc in exceptions:
        if term not in exc:
            continue
        offset = exc.find(term)
        while offset != -1:
            win_start = pos - offset
            win_end = win_start + len(exc)
            if win_start >= 0 and win_end <= len(text) and text[win_start:win_end] == exc:
                return True
            offset = exc.find(term, offset + 1)
    return False


def _make_context(text: str, start: int, end: int) -> str:
    """擷取命中詞前後各 CONTEXT_CHARS 字，命中詞以【】標示。"""
    prefix = text[max(0, start - CONTEXT_CHARS):start]
    suffix = text[end:end + CONTEXT_CHARS]
    return f"{prefix}【{text[start:end]}】{suffix}"


def find_hits(
    text: str,
    rules: Sequence[Rule],
    levels: Optional[Iterable[str]] = None,
) -> List[Hit]:
    """在 text 中比對 rules，回傳命中清單（純函式）。

    - 僅比對「啟用＝是」且風險等級在 levels 內的規則。
    - 最長詞優先：同一起點取最長可命中的詞，命中後跳過該區段。
    - 套用例外詞過濾。

    levels 預設為 {高, 中}。
    """
    if levels is None:
        levels = DEFAULT_LEVELS
    levels = set(levels)

    # 候選規則：啟用且等級符合。以 (詞長遞減, 原順序) 排序，落實最長詞優先。
    candidates = [
        r for r in rules
        if r.enabled and r.risk in levels and r.term
    ]
    candidates.sort(key=lambda r: -len(r.term))

    hits: List[Hit] = []
    i = 0
    n = len(text)
    while i < n:
        matched: Optional[Rule] = None
        for rule in candidates:
            term = rule.term
            end = i + len(term)
            if end > n:
                continue
            if text[i:end] != term:
                continue
            if _is_excepted(text, i, term, rule.exceptions):
                # 落在例外詞內 → 略過此規則，繼續嘗試其他（可能較短的）候選詞。
                continue
            matched = rule
            break
        if matched is not None:
            end = i + len(matched.term)
            hits.append(Hit(
                term=matched.term,
                suggestion=matched.suggestion,
                risk=matched.risk,
                start=i,
                end=end,
                context=_make_context(text, i, end),
                category=matched.category,
                note=matched.note,
                source_id=matched.source_id,
            ))
            i = end  # 命中後跳過整個區段，不以較短詞重複命中。
        else:
            i += 1
    return hits


def load_rules(csv_path: str) -> Tuple[List[Rule], List[str]]:
    """從詞庫 CSV 讀取規則，回傳 (規則清單, 警告訊息清單)。

    - 編碼：UTF-8 with BOM（以 utf-8-sig 讀取）。
    - 支援六欄（舊版）與八欄（含例外詞、啟用）格式。
    - 六欄格式：例外詞視為空、啟用＝是，並套用 KNOWN_EXCEPTIONS 作為安全網。
    - 中國用語欄若含「／」拆為多筆規則。
    """
    warnings: List[str] = []
    rules: List[Rule] = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        has_exceptions = "例外詞" in fieldnames
        has_enabled = "啟用" in fieldnames
        required = {"中國用語", "台灣慣用語", "風險等級"}
        missing = required - set(fieldnames)
        if missing:
            raise ValueError(
                "詞庫 CSV 欄位格式錯誤，缺少必要欄位：" + "、".join(sorted(missing))
            )
        if not has_exceptions or not has_enabled:
            warnings.append(
                "詞庫為舊版格式（缺少「例外詞」或「啟用」欄位）；"
                "已套用內建預設例外詞，建議升級為八欄格式。"
            )

        for row in reader:
            raw_term = (row.get("中國用語") or "").strip()
            if not raw_term:
                continue
            suggestion = (row.get("台灣慣用語") or "").strip()
            risk = (row.get("風險等級") or "").strip()
            category = (row.get("類別") or "").strip()
            note = (row.get("備註") or "").strip()
            source_id = (row.get("編號") or "").strip()

            enabled = True
            if has_enabled:
                enabled = (row.get("啟用") or "是").strip() != "否"

            csv_exceptions = (
                _split_exceptions(row.get("例外詞") or "") if has_exceptions else []
            )

            for term in _split_terms(raw_term):
                # 例外詞：優先採用 CSV；舊版格式則以 KNOWN_EXCEPTIONS 補上。
                if csv_exceptions:
                    exceptions = list(csv_exceptions)
                elif not has_exceptions:
                    exceptions = list(KNOWN_EXCEPTIONS.get(term, []))
                else:
                    exceptions = []
                rules.append(Rule(
                    term=term,
                    suggestion=suggestion,
                    risk=risk,
                    category=category,
                    note=note,
                    exceptions=exceptions,
                    enabled=enabled,
                    source_id=source_id,
                ))

    return rules, warnings
