/* 比對引擎（JS 版）單元測試，對應 test_matcher.py 的最低案例。
 * 執行：node test_matcher.js
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const M = require("./matcher.js");

const HEADER8 = "編號,中國用語,台灣慣用語,類別,風險等級,備註,例外詞,啟用\n";
const HEADER6 = "編號,中國用語,台灣慣用語,類別,風險等級,備註\n";

function rulesFrom(csv) { return M.loadRules(csv).rules; }
const terms = hits => hits.map(h => h.term);

const tests = {
  "花生粉不應命中生粉"() {
    const rules = rulesFrom(HEADER8 + "1,生粉,太白粉,飲食,中,,花生粉;花生醬,是\n");
    assert.deepStrictEqual(terms(M.findHits("這道菜加花生粉", rules)), []);
    assert.deepStrictEqual(terms(M.findHits("勾芡用生粉", rules)), ["生粉"]);
  },
  "電影院不應命中影院"() {
    const rules = rulesFrom(HEADER8 + "1,影院,電影院／戲院,影視娛樂,中,,電影院,是\n");
    assert.deepStrictEqual(terms(M.findHits("週末去電影院", rules)), []);
    assert.deepStrictEqual(terms(M.findHits("附近的影院", rules)), ["影院"]);
  },
  "小黃瓜不應命中黃瓜"() {
    const rules = rulesFrom(HEADER8 + "1,黃瓜,小黃瓜,飲食,中,,小黃瓜;大黃瓜,是\n");
    assert.deepStrictEqual(terms(M.findHits("涼拌小黃瓜", rules)), []);
    assert.deepStrictEqual(terms(M.findHits("涼拌黃瓜", rules)), ["黃瓜"]);
  },
  "最長詞優先：沒過食材只命中一次"() {
    const rules = rulesFrom(HEADER8 +
      "1,沒過,蓋過,料理烹飪,高,,,是\n2,沒過食材,蓋過食材,料理烹飪,高,,,是\n");
    const hits = M.findHits("加水沒過食材", rules);
    assert.strictEqual(hits.length, 1);
    assert.strictEqual(hits[0].term, "沒過食材");
  },
  "視頻與質量各命中一次且位置正確"() {
    const rules = rulesFrom(HEADER8 +
      "1,視頻,影片,資訊科技,高,,,是\n2,質量,品質,資訊科技,高,,,是\n");
    const hits = M.findHits("這個視頻的質量很好", rules);
    assert.deepStrictEqual(hits.map(h => [h.term, h.start]), [["視頻", 2], ["質量", 5]]);
    assert.strictEqual(hits[0].context, "這個【視頻】的質量很好");
  },
  "停用規則不得命中"() {
    const rules = rulesFrom(HEADER8 + "1,視頻,影片,資訊科技,高,,,否\n");
    assert.deepStrictEqual(M.findHits("看視頻", rules), []);
  },
  "預設只檢查高與中"() {
    const rules = rulesFrom(HEADER8 +
      "1,視頻,影片,資訊科技,高,,,是\n2,立馬,馬上,日常生活,低,,,是\n");
    assert.deepStrictEqual(terms(M.findHits("立馬看視頻", rules)), ["視頻"]);
    assert.deepStrictEqual(terms(M.findHits("立馬看視頻", rules, M.ALL_LEVELS)), ["立馬", "視頻"]);
  },
  "中國用語欄以／拆為多筆"() {
    const rules = rulesFrom(HEADER8 + "1,賬號／賬戶,帳號／帳戶,資訊科技,高,,,是\n");
    assert.deepStrictEqual(rules.map(r => r.term), ["賬號", "賬戶"]);
    assert.strictEqual(rules[1].suggestion, "帳號／帳戶");
  },
  "例外詞支援半形與全形分號"() {
    const rules = rulesFrom(HEADER8 + "1,生粉,太白粉,飲食,中,,花生粉；花生醬,是\n");
    assert.deepStrictEqual(rules[0].exceptions, ["花生粉", "花生醬"]);
  },
  "六欄舊格式套用內建例外詞並提出警告"() {
    const { rules, warnings } = M.loadRules(HEADER6 + "1,生粉,太白粉,飲食,中,\n");
    assert.strictEqual(warnings.length, 1);
    assert.deepStrictEqual(terms(M.findHits("花生粉", rules)), []);
  },
  "缺必要欄位時拋錯"() {
    assert.throws(() => M.loadRules("編號,詞\n1,x\n"), /缺少必要欄位/);
  },
  "CSV 解析：引號、逗號、換行、BOM"() {
    const rows = M.parseCsv('﻿a,b\n"x,1","多行\n值"\r\n"引""號",z\n');
    assert.deepStrictEqual(rows, [["a", "b"], ["x,1", "多行\n值"], ['引"號', "z"]]);
  },
  "checkUnits：低風險不影響通過判定"() {
    const rules = rulesFrom(HEADER8 +
      "1,視頻,影片,資訊科技,高,,,是\n2,立馬,馬上,日常生活,低,,,是\n");
    const r = M.checkUnits([["第 1 行", "看視頻"], ["第 2 行", "立馬去"], ["第 3 行", "乾淨"]],
      rules, M.ALL_LEVELS);
    assert.strictEqual(r.totalUnits, 3);
    assert.strictEqual(r.failedUnits, 1);
    assert.strictEqual(r.passedUnits, 2);
    assert.strictEqual(r.totalHits, 2);
    assert.strictEqual(r.hitsByRisk["低"], 1);
  },
  "真實詞庫：關鍵案例"() {
    const csv = fs.readFileSync(path.join(__dirname, "中國用語對照資料庫.csv"), "utf8");
    const { rules, warnings } = M.loadRules(csv);
    assert.deepStrictEqual(warnings, []);
    assert.ok(rules.length > 500);
    for (const t of ["這道菜加花生粉", "週末去電影院", "涼拌小黃瓜", "依標準程序辦理",
                     "練出馬甲線", "用橡皮筋綁好", "面臨期末考", "碳水化合物含量高"]) {
      assert.deepStrictEqual(terms(M.findHits(t, rules)), [], t);
    }
    assert.deepStrictEqual(terms(M.findHits("這個視頻的質量很好", rules)), ["視頻", "質量"]);
    assert.deepStrictEqual(terms(M.findHits("加水沒過食材，加點生粉", rules)), ["沒過食材", "生粉"]);
  },
};

let passed = 0, failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { fn(); passed++; console.log("ok   " + name); }
  catch (e) { failed++; console.log("FAIL " + name + "\n     " + e.message); }
}
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
