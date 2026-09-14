# -*- coding: utf-8 -*-
"""檢查流程協調層與報告輸出層單元測試。

執行：python3 -m unittest test_report -v
"""

import os
import tempfile
import unittest
from datetime import datetime

from checker import check_units
from matcher import ALL_LEVELS, Rule
from report import build_report_path, write_report


def rule(term, suggestion="建議", risk="高", **kw):
    return Rule(term=term, suggestion=suggestion, risk=risk, **kw)


RULES = [
    rule("視頻", "影片", "高", category="資訊科技"),
    rule("質量", "品質", "高"),
    rule("接地氣", "在地", "中"),
    rule("立馬", "馬上", "低"),
]


class CheckUnitsTests(unittest.TestCase):
    def test_統計與明細(self):
        units = [
            ("第 1 行", "這個視頻的質量很好"),  # 未通過（高×2）
            ("第 2 行", "完全沒有問題的一句話"),  # 通過
            ("第 3 行", "文案要接地氣"),          # 未通過（中×1）
        ]
        result = check_units(units, RULES)
        self.assertEqual(result.total_units, 3)
        self.assertEqual(result.failed_units, 2)
        self.assertEqual(result.passed_units, 1)
        self.assertEqual(result.total_hits, 3)
        counts = result.hits_by_risk()
        self.assertEqual(counts["高"], 2)
        self.assertEqual(counts["中"], 1)

    def test_低風險不影響通過判定(self):
        units = [("第 1 行", "立馬處理")]
        result = check_units(units, RULES, levels=set(ALL_LEVELS))
        self.assertEqual(result.total_hits, 1)      # 低風險有列出
        self.assertEqual(result.failed_units, 0)    # 但不算未通過
        self.assertEqual(result.passed_units, 1)

    def test_預設等級不含低(self):
        units = [("第 1 行", "立馬處理")]
        result = check_units(units, RULES)
        self.assertEqual(result.total_hits, 0)

    def test_位置字串保留(self):
        units = [("工作表1!B5", "看視頻")]
        result = check_units(units, RULES)
        self.assertEqual(result.unit_hits[0].position, "工作表1!B5")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _make_report(self):
        units = [
            ("第 1 行", "這個視頻的質量很好"),
            ("第 2 行", "文案要接地氣"),
            ("第 3 行", "立馬處理"),
        ]
        result = check_units(units, RULES, levels=set(ALL_LEVELS))
        src = os.path.join(self.tmp.name, "測試文案.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x")
        lexicon = os.path.join(self.tmp.name, "中國用語對照資料庫.csv")
        with open(lexicon, "w", encoding="utf-8") as f:
            f.write("x")
        now = datetime(2026, 7, 13, 14, 30, 5)
        path = build_report_path(src, self.tmp.name, now=now)
        write_report(path, src, result, lexicon, rule_count=len(RULES), now=now)
        return path, result

    def test_檔名與資料夾(self):
        path, _ = self._make_report()
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.basename(os.path.dirname(path)), "檢查報告")
        self.assertEqual(
            os.path.basename(path), "測試文案_檢查報告_20260713_143005.xlsx"
        )

    def test_總覽內容(self):
        path, result = self._make_report()
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb["總覽"]
        data = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, 20)}
        self.assertEqual(data["受檢檔名"], "測試文案.txt")
        self.assertEqual(data["詞庫規則數"], 4)
        self.assertEqual(data["檢查等級設定"], "高＋中＋低")
        self.assertEqual(data["掃描單元數"], 3)
        self.assertEqual(data["未通過數"], 2)   # 低風險那行不算未通過
        self.assertEqual(data["通過數"], 1)
        self.assertEqual(data["高風險命中數"], 2)
        self.assertEqual(data["中風險命中數"], 1)
        self.assertEqual(data["低風險命中數（僅供參考）"], 1)

    def test_明細內容與格式(self):
        path, result = self._make_report()
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb["明細"]
        headers = [ws.cell(1, c).value for c in range(1, 8)]
        self.assertEqual(
            headers, ["位置", "命中詞", "修改建議", "風險等級", "前後文", "類別", "備註"]
        )
        # 明細列數 = 命中數
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(rows), result.total_hits)
        # 第一筆：視頻
        self.assertEqual(rows[0][0], "第 1 行")
        self.assertEqual(rows[0][1], "視頻")
        self.assertEqual(rows[0][2], "影片")
        self.assertIn("【視頻】", rows[0][4])
        self.assertEqual(rows[0][5], "資訊科技")
        # 凍結首列與自動篩選
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertEqual(ws.auto_filter.ref, f"A1:G{result.total_hits + 1}")

    def test_風險上色(self):
        path, _ = self._make_report()
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb["明細"]
        fills = {}
        for row in ws.iter_rows(min_row=2):
            risk = row[3].value
            fills[risk] = row[3].fill.start_color.rgb
        self.assertEqual(fills["高"], "00FFC7CE")  # 紅
        self.assertEqual(fills["中"], "00FFD8A8")  # 橘
        self.assertEqual(fills["低"], "00C6EFCE")  # 綠

    def test_零命中仍可產出報告(self):
        result = check_units([("第 1 行", "乾淨的句子")], RULES)
        src = os.path.join(self.tmp.name, "乾淨.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x")
        path = build_report_path(src, self.tmp.name)
        write_report(path, src, result, "不存在的詞庫.csv", rule_count=4)
        self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
