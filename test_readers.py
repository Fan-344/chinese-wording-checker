# -*- coding: utf-8 -*-
"""檔案讀取層單元測試。

執行：python3 -m unittest test_readers -v
"""

import os
import tempfile
import unittest

from readers import FileReadError, read_csv, read_file, read_txt, read_xlsx


class _TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)


class TxtReaderTests(_TempDirTestCase):
    def test_逐行且位置正確(self):
        p = self.path("a.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("第一行文字\n\n第三行文字\n")
        units = read_txt(p)
        # 空行跳過
        self.assertEqual(units, [("第 1 行", "第一行文字"), ("第 3 行", "第三行文字")])

    def test_utf8_bom(self):
        p = self.path("bom.txt")
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write("視頻測試\n")
        self.assertEqual(read_txt(p), [("第 1 行", "視頻測試")])

    def test_cp950(self):
        p = self.path("big5.txt")
        with open(p, "w", encoding="cp950") as f:
            f.write("繁體中文內容\n")
        self.assertEqual(read_txt(p), [("第 1 行", "繁體中文內容")])

    def test_孤立CR與U2028不影響行號(self):
        # 迴歸測試：檔案中的孤立 \r 或 U+2028 不得當成換行，
        # 行號須與編輯器（以 \n 計行）一致。
        p = self.path("cr.txt")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("第一行有孤立\r符號\n奇怪 分隔\n第三行\n")
        units = read_txt(p)
        self.assertEqual([pos for pos, _ in units],
                         ["第 1 行", "第 2 行", "第 3 行"])
        self.assertEqual(units[2], ("第 3 行", "第三行"))

    def test_crlf_換行(self):
        p = self.path("crlf.txt")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("第一行\r\n第二行\r\n")
        self.assertEqual(read_txt(p),
                         [("第 1 行", "第一行"), ("第 2 行", "第二行")])

    def test_無法辨識編碼(self):
        p = self.path("bad.txt")
        with open(p, "wb") as f:
            f.write(b"\xff\xfe\x00\xd8\x00\xdc")  # 非 UTF-8 亦非 CP950
        with self.assertRaises(FileReadError):
            read_txt(p)


class CsvReaderTests(_TempDirTestCase):
    def test_逐格且位置正確(self):
        p = self.path("a.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("標題,內文\n文案一,這個視頻很好\n")
        units = read_csv(p)
        self.assertIn(("第 1 列第 1 欄", "標題"), units)
        self.assertIn(("第 2 列第 2 欄", "這個視頻很好"), units)
        self.assertEqual(len(units), 4)

    def test_空儲存格跳過(self):
        p = self.path("b.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("a,,c\n")
        self.assertEqual(
            read_csv(p),
            [("第 1 列第 1 欄", "a"), ("第 1 列第 3 欄", "c")],
        )

    def test_cp950_編碼(self):
        p = self.path("big5.csv")
        with open(p, "w", encoding="cp950", newline="") as f:
            f.write("欄一,欄二\n質量,測試\n")
        units = read_csv(p)
        self.assertIn(("第 2 列第 1 欄", "質量"), units)


class XlsxReaderTests(_TempDirTestCase):
    def _make_xlsx(self, name="a.xlsx"):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "工作表1"
        ws["A1"] = "標題"
        ws["B2"] = "這個視頻很好"
        ws["C3"] = 12345          # 數字 → 跳過
        ws["D4"] = "   "          # 空白字串 → 跳過
        ws2 = wb.create_sheet("第二頁")
        ws2["A5"] = "質量檢查"
        p = self.path(name)
        wb.save(p)
        return p

    def test_逐儲存格且位置為_工作表名_A5(self):
        units = read_xlsx(self._make_xlsx())
        self.assertIn(("工作表1!A1", "標題"), units)
        self.assertIn(("工作表1!B2", "這個視頻很好"), units)
        self.assertIn(("第二頁!A5", "質量檢查"), units)

    def test_僅讀字串儲存格(self):
        units = read_xlsx(self._make_xlsx())
        positions = [pos for pos, _ in units]
        self.assertNotIn("工作表1!C3", positions)  # 數字
        self.assertNotIn("工作表1!D4", positions)  # 純空白

    def test_指定欄位(self):
        units = read_xlsx(self._make_xlsx(), columns=["B"])
        self.assertEqual(units, [("工作表1!B2", "這個視頻很好")])

    def test_指定欄位_空清單等同全部(self):
        self.assertEqual(
            read_xlsx(self._make_xlsx(), columns=[]),
            read_xlsx(self._make_xlsx()),
        )


class ReadFileDispatchTests(_TempDirTestCase):
    def test_依副檔名分派(self):
        p = self.path("a.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("內容\n")
        self.assertEqual(read_file(p), [("第 1 行", "內容")])

    def test_副檔名大小寫不敏感(self):
        p = self.path("A.TXT")
        with open(p, "w", encoding="utf-8") as f:
            f.write("內容\n")
        self.assertEqual(read_file(p), [("第 1 行", "內容")])

    def test_不支援格式拋錯(self):
        p = self.path("a.docx")
        with open(p, "w") as f:
            f.write("x")
        with self.assertRaises(FileReadError):
            read_file(p)

    def test_檔案不存在拋錯(self):
        with self.assertRaises(FileReadError):
            read_file(self.path("不存在.txt"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
