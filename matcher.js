/* 中國用語檢查工具 — 比對引擎（JavaScript 版，與 matcher.py 行為一致）。
 *
 * 純函式、不依賴 DOM，可同時在瀏覽器與 Node 執行（Node 用於單元測試）。
 * - 最長詞優先：同一起點先比對長詞，命中後該區段不再以較短詞重複命中。
 * - 例外詞過濾：命中位置的上下文若構成任一例外詞則跳過。
 * - 僅比對「啟用＝是」的規則；風險等級預設「高＋中」。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Matcher = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RISK_HIGH = "高";
  const RISK_MID = "中";
  const RISK_LOW = "低";
  const DEFAULT_LEVELS = [RISK_HIGH, RISK_MID];
  const ALL_LEVELS = [RISK_HIGH, RISK_MID, RISK_LOW];
  const BLOCKING_LEVELS = new Set([RISK_HIGH, RISK_MID]);
  const CONTEXT_CHARS = 18;

  const TERM_SEPARATORS = ["／", "/"];
  const EXCEPTION_SEPARATORS = [";", "；"];

  const KNOWN_EXCEPTIONS = {
    "生粉": ["花生粉", "花生醬"],
    "影院": ["電影院"],
    "線下": ["光線下"],
    "薯片": ["馬鈴薯片"],
    "黃瓜": ["小黃瓜", "大黃瓜"],
    "菠蘿": ["菠蘿油", "菠蘿包"],
    "就這": ["就這樣", "就這麼"],
    "程序": ["標準程序", "法律程序", "行政程序"],
  };

  // ---- CSV 解析（RFC 4180：支援引號、引號內逗號與換行、\r\n） ----
  function parseCsv(text) {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inQuotes) {
        if (ch === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += ch;
      } else if (ch === '"') inQuotes = true;
      else if (ch === ",") { row.push(field); field = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        rows.push(row); row = [];
      } else field += ch;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
  }

  function csvToObjects(text) {
    const rows = parseCsv(text).filter(r => r.some(c => c.trim() !== ""));
    if (!rows.length) return { fieldnames: [], records: [] };
    const fieldnames = rows[0].map(h => h.trim());
    const records = rows.slice(1).map(r => {
      const o = {};
      fieldnames.forEach((h, i) => { o[h] = r[i] !== undefined ? r[i] : ""; });
      return o;
    });
    return { fieldnames, records };
  }

  function splitBy(raw, seps) {
    let parts = [raw];
    for (const sep of seps) parts = parts.flatMap(p => p.split(sep));
    return parts.map(p => p.trim()).filter(Boolean);
  }

  // ---- 規則載入 ----
  function loadRules(csvText) {
    const warnings = [];
    const rules = [];
    const { fieldnames, records } = csvToObjects(csvText);
    const hasExceptions = fieldnames.includes("例外詞");
    const hasEnabled = fieldnames.includes("啟用");
    const missing = ["中國用語", "台灣慣用語", "風險等級"].filter(f => !fieldnames.includes(f));
    if (missing.length) {
      throw new Error("詞庫 CSV 欄位格式錯誤，缺少必要欄位：" + missing.join("、"));
    }
    if (!hasExceptions || !hasEnabled) {
      warnings.push("詞庫為舊版格式（缺少「例外詞」或「啟用」欄位）；已套用內建預設例外詞，建議升級為八欄格式。");
    }
    for (const row of records) {
      const rawTerm = (row["中國用語"] || "").trim();
      if (!rawTerm) continue;
      const suggestion = (row["台灣慣用語"] || "").trim();
      const risk = (row["風險等級"] || "").trim();
      const category = (row["類別"] || "").trim();
      const note = (row["備註"] || "").trim();
      const sourceId = (row["編號"] || "").trim();
      const enabled = hasEnabled ? (row["啟用"] || "是").trim() !== "否" : true;
      const csvExceptions = hasExceptions ? splitBy(row["例外詞"] || "", EXCEPTION_SEPARATORS) : [];
      for (const term of splitBy(rawTerm, TERM_SEPARATORS)) {
        let exceptions;
        if (csvExceptions.length) exceptions = csvExceptions.slice();
        else if (!hasExceptions) exceptions = (KNOWN_EXCEPTIONS[term] || []).slice();
        else exceptions = [];
        rules.push({ term, suggestion, risk, category, note, exceptions, enabled, sourceId });
      }
    }
    return { rules, warnings };
  }

  // ---- 比對 ----
  function isExcepted(text, pos, term, exceptions) {
    for (const exc of exceptions) {
      let offset = exc.indexOf(term);
      while (offset !== -1) {
        const winStart = pos - offset;
        const winEnd = winStart + exc.length;
        if (winStart >= 0 && winEnd <= text.length && text.slice(winStart, winEnd) === exc) return true;
        offset = exc.indexOf(term, offset + 1);
      }
    }
    return false;
  }

  function makeContext(text, start, end) {
    const prefix = text.slice(Math.max(0, start - CONTEXT_CHARS), start);
    const suffix = text.slice(end, end + CONTEXT_CHARS);
    return prefix + "【" + text.slice(start, end) + "】" + suffix;
  }

  function findHits(text, rules, levels) {
    const levelSet = new Set(levels || DEFAULT_LEVELS);
    const candidates = rules
      .filter(r => r.enabled && levelSet.has(r.risk) && r.term)
      .map((r, i) => ({ r, i }))
      .sort((a, b) => (b.r.term.length - a.r.term.length) || (a.i - b.i))
      .map(x => x.r);
    const hits = [];
    const n = text.length;
    let i = 0;
    while (i < n) {
      let matched = null;
      for (const rule of candidates) {
        const end = i + rule.term.length;
        if (end > n) continue;
        if (text.slice(i, end) !== rule.term) continue;
        if (isExcepted(text, i, rule.term, rule.exceptions)) continue;
        matched = rule;
        break;
      }
      if (matched) {
        const end = i + matched.term.length;
        hits.push({
          term: matched.term, suggestion: matched.suggestion, risk: matched.risk,
          start: i, end, context: makeContext(text, i, end),
          category: matched.category, note: matched.note, sourceId: matched.sourceId,
        });
        i = end;
      } else i++;
    }
    return hits;
  }

  // ---- 檢查流程：units = [[位置字串, 文字], ...] ----
  function checkUnits(units, rules, levels) {
    const levelList = levels || DEFAULT_LEVELS;
    const result = { levels: levelList.slice(), totalUnits: units.length, failedUnits: 0, unitHits: [] };
    for (const [position, text] of units) {
      const hits = findHits(text, rules, levelList);
      if (hits.some(h => BLOCKING_LEVELS.has(h.risk))) result.failedUnits++;
      for (const hit of hits) result.unitHits.push({ position, hit });
    }
    result.passedUnits = result.totalUnits - result.failedUnits;
    result.totalHits = result.unitHits.length;
    result.hitsByRisk = { [RISK_HIGH]: 0, [RISK_MID]: 0, [RISK_LOW]: 0 };
    for (const uh of result.unitHits) {
      result.hitsByRisk[uh.hit.risk] = (result.hitsByRisk[uh.hit.risk] || 0) + 1;
    }
    return result;
  }

  return {
    RISK_HIGH, RISK_MID, RISK_LOW, DEFAULT_LEVELS, ALL_LEVELS, CONTEXT_CHARS,
    KNOWN_EXCEPTIONS, parseCsv, csvToObjects, loadRules, findHits, checkUnits,
  };
});
