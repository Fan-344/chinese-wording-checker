# -*- coding: utf-8 -*-
"""比對引擎單元測試（規格書第 4 節「單元測試最低案例」＋補充案例）。

執行：python3 -m unittest test_matcher -v
"""

import os
import tempfile
import unittest

from matcher import (
    ALL_LEVELS,
    DEFAULT_LEVELS,
    Rule,
    find_hits,
    load_rules,
)


def rule(term, suggestion="建議", risk="高", exceptions=None, enabled=True, category="", note=""):
    return Rule(
        term=term,
        suggestion=suggestion,
        risk=risk,
        exceptions=list(exceptions or []),
        enabled=enabled,
        category=category,
        note=note,
    )


class ExceptionFilterTests(unittest.TestCase):
    """例外詞過濾：解決子字串誤判。"""

    def test_花生粉_不得命中_生粉(self):
        rules = [rule("生粉", exceptions=["花生粉", "花生醬"])]
        self.assertEqual(find_hits("這道菜要加花生粉調味", rules), [])

    def test_純生粉_仍應命中(self):
        # 例外詞不應讓正當命中失效。
        rules = [rule("生粉", exceptions=["花生粉", "花生醬"])]
        hits = find_hits("勾芡用生粉即可", rules)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].term, "生粉")

    def test_電影院_不得命中_影院(self):
        rules = [rule("影院", exceptions=["電影院"])]
        self.assertEqual(find_hits("我們去電影院看戲", rules), [])

    def test_小黃瓜_不得命中_黃瓜(self):
        rules = [rule("黃瓜", exceptions=["小黃瓜", "大黃瓜"])]
        self.assertEqual(find_hits("涼拌小黃瓜很爽口", rules), [])

    def test_黃瓜_單獨仍命中(self):
        rules = [rule("黃瓜", exceptions=["小黃瓜", "大黃瓜"])]
        hits = find_hits("這條黃瓜很新鮮", rules)
        self.assertEqual(len(hits), 1)

    def test_光線下_不得命中_線下(self):
        rules = [rule("線下", exceptions=["光線下"])]
        self.assertEqual(find_hits("在光線下觀察顏色", rules), [])


class LongestMatchTests(unittest.TestCase):
    """最長詞優先。"""

    def test_沒過食材_命中一次_不得同時回報沒過(self):
        rules = [
            rule("沒過食材", suggestion="蓋過食材"),
            rule("沒過", suggestion="淹過"),  # 較短詞，不得在同區段重複命中
        ]
        hits = find_hits("加水沒過食材即可", rules)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].term, "沒過食材")

    def test_沒過_在別處仍可獨立命中(self):
        rules = [rule("沒過食材"), rule("沒過")]
        hits = find_hits("水沒過鍋底", rules)
        self.assertEqual([h.term for h in hits], ["沒過"])


class PositionAndCountTests(unittest.TestCase):
    """位置與次數正確性。"""

    def test_視頻_質量_各命中一次_位置正確(self):
        rules = [rule("視頻", suggestion="影片"), rule("質量", suggestion="品質")]
        text = "這個視頻的質量很好"
        #        這0 個1 視2 頻3 的4 質5 量6 很7 好8
        hits = find_hits(text, rules)
        self.assertEqual(len(hits), 2)
        by_term = {h.term: h for h in hits}
        self.assertEqual(by_term["視頻"].start, 2)
        self.assertEqual(by_term["質量"].start, 5)

    def test_重複詞_多次命中(self):
        rules = [rule("視頻")]
        hits = find_hits("視頻又是視頻", rules)
        self.assertEqual(len(hits), 2)
        self.assertEqual([h.start for h in hits], [0, 4])

    def test_context_標示命中詞(self):
        rules = [rule("質量", suggestion="品質")]
        hits = find_hits("這個視頻的質量很好", rules)
        self.assertEqual(hits[0].context, "這個視頻的【質量】很好")


class EnabledFilterTests(unittest.TestCase):
    def test_停用規則不得命中(self):
        rules = [rule("視頻", enabled=False)]
        self.assertEqual(find_hits("這個視頻很好", rules), [])

    def test_啟用規則命中(self):
        rules = [rule("視頻", enabled=True)]
        self.assertEqual(len(find_hits("這個視頻很好", rules)), 1)


class RiskLevelTests(unittest.TestCase):
    def test_預設只檢查高與中(self):
        rules = [rule("低詞", risk="低"), rule("中詞", risk="中"), rule("高詞", risk="高")]
        hits = find_hits("低詞中詞高詞", rules)  # 預設 levels
        self.assertEqual({h.term for h in hits}, {"中詞", "高詞"})

    def test_指定包含低等級(self):
        rules = [rule("低詞", risk="低")]
        self.assertEqual(len(find_hits("低詞", rules, levels=ALL_LEVELS)), 1)

    def test_預設常數為高中(self):
        self.assertEqual(DEFAULT_LEVELS, {"高", "中"})


class LoadRulesTests(unittest.TestCase):
    """詞庫讀取層（六欄與八欄）。"""

    def _write_csv(self, content):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_八欄格式_例外詞與啟用(self):
        csv_text = (
            "編號,中國用語,台灣慣用語,類別,風險等級,備註,例外詞,啟用\n"
            "1,生粉,太白粉,飲食,中,粵語,花生粉;花生醬,是\n"
            "2,視頻,影片,資訊科技,高,,,否\n"
        )
        rules, warnings = load_rules(self._write_csv(csv_text))
        self.assertEqual(warnings, [])
        by_term = {r.term: r for r in rules}
        self.assertEqual(by_term["生粉"].exceptions, ["花生粉", "花生醬"])
        self.assertTrue(by_term["生粉"].enabled)
        self.assertFalse(by_term["視頻"].enabled)
        # 停用規則不參與比對。
        self.assertEqual(find_hits("這個視頻很好", rules), [])
        # 例外詞生效。
        self.assertEqual(find_hits("加點花生粉", rules), [])

    def test_六欄格式_套用內建例外詞並警告(self):
        csv_text = (
            "編號,中國用語,台灣慣用語,類別,風險等級,備註\n"
            "1,生粉,太白粉,飲食,中,粵語\n"
            "2,影院,電影院／戲院,影視娛樂,中,\n"
        )
        rules, warnings = load_rules(self._write_csv(csv_text))
        self.assertTrue(warnings)  # 應提示升級詞庫格式
        by_term = {r.term: r for r in rules}
        self.assertEqual(by_term["生粉"].exceptions, ["花生粉", "花生醬"])
        # 舊版格式下仍不誤判。
        self.assertEqual(find_hits("這道菜加花生粉", rules), [])
        self.assertEqual(find_hits("我們去電影院", rules), [])

    def test_中國用語含斜線_拆成多筆(self):
        csv_text = (
            "編號,中國用語,台灣慣用語,類別,風險等級,備註,例外詞,啟用\n"
            "1,賬號／賬戶,帳號／帳戶,資訊科技,高,,,是\n"
        )
        rules, _ = load_rules(self._write_csv(csv_text))
        terms = {r.term for r in rules}
        self.assertEqual(terms, {"賬號", "賬戶"})
        hits = find_hits("請輸入賬號與賬戶", rules)
        self.assertEqual({h.term for h in hits}, {"賬號", "賬戶"})

    def test_缺少必要欄位拋錯(self):
        csv_text = "編號,台灣慣用語\n1,影片\n"
        with self.assertRaises(ValueError):
            load_rules(self._write_csv(csv_text))


class RealDatabaseTests(unittest.TestCase):
    """對實際詞庫檔（若存在）做煙霧測試。"""

    DB = os.path.join(os.path.dirname(__file__), "中國用語對照資料庫.csv")

    def setUp(self):
        if not os.path.exists(self.DB):
            self.skipTest("找不到詞庫檔")
        self.rules, self.warnings = load_rules(self.DB)

    def test_可讀取且有規則(self):
        self.assertGreater(len(self.rules), 100)

    def test_實際詞庫下花生粉不誤判(self):
        self.assertEqual(find_hits("這道菜要加花生粉", self.rules), [])

    def test_實際詞庫下電影院不誤判(self):
        self.assertEqual(find_hits("週末去電影院", self.rules), [])

    def test_實際詞庫命中視頻與質量(self):
        hits = find_hits("這個視頻的質量很好", self.rules)
        self.assertIn("視頻", {h.term for h in hits})
        self.assertIn("質量", {h.term for h in hits})


if __name__ == "__main__":
    unittest.main(verbosity=2)
