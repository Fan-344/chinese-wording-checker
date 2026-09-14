# -*- coding: utf-8 -*-
"""中國用語檢查工具 — 檢查流程協調層。

串接讀取層與比對引擎：對一個檔案的所有掃描單元跑比對，
彙整成報告輸出與 GUI 摘要所需的結果物件。

通過判定原則（規格書第 4、6 節）：
「低」風險僅列為參考，不影響通過判定 —— 一個掃描單元只有在
命中「高」或「中」風險詞時才算未通過。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Set, Tuple

from matcher import DEFAULT_LEVELS, RISK_HIGH, RISK_LOW, RISK_MID, Hit, Rule, find_hits
from readers import Unit

# 影響通過判定的等級（「低」僅供參考）。
BLOCKING_LEVELS = {RISK_HIGH, RISK_MID}


@dataclass
class UnitHit:
    """一筆明細：某掃描單元中的一次命中。"""

    position: str  # 位置字串（如「第 3 行」「工作表1!B5」）
    hit: Hit


@dataclass
class CheckResult:
    """單一檔案的檢查結果。"""

    levels: Set[str]                 # 本次檢查的等級集合
    total_units: int = 0             # 掃描單元數
    failed_units: int = 0            # 未通過數（命中高／中的單元）
    unit_hits: List[UnitHit] = field(default_factory=list)

    @property
    def passed_units(self) -> int:
        return self.total_units - self.failed_units

    @property
    def total_hits(self) -> int:
        return len(self.unit_hits)

    def hits_by_risk(self) -> dict:
        counts = {RISK_HIGH: 0, RISK_MID: 0, RISK_LOW: 0}
        for uh in self.unit_hits:
            counts[uh.hit.risk] = counts.get(uh.hit.risk, 0) + 1
        return counts


def check_units(
    units: Sequence[Unit],
    rules: Sequence[Rule],
    levels: Set[str] = None,
) -> CheckResult:
    """對掃描單元清單執行比對，回傳彙整結果（純函式）。"""
    if levels is None:
        levels = set(DEFAULT_LEVELS)
    levels = set(levels)

    result = CheckResult(levels=levels, total_units=len(units))
    for position, text in units:
        hits = find_hits(text, rules, levels=levels)
        if any(h.risk in BLOCKING_LEVELS for h in hits):
            result.failed_units += 1
        for h in hits:
            result.unit_hits.append(UnitHit(position=position, hit=h))
    return result
