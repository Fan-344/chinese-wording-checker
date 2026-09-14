/* 中國用語檢查工具 — 網頁版（GitHub Pages 靜態站，所有處理皆在瀏覽器內完成）。
 * 依賴：matcher.js（比對引擎）、ExcelJS（讀寫 .xlsx，CDN 載入）。
 */
(function () {
  "use strict";

  const CSV_NAME = "中國用語對照資料庫.csv";
  const SUPPORTED = [".txt", ".csv", ".xlsx"];
  const M = window.Matcher;

  const state = {
    rules: [], warnings: [], ruleCount: 0,
    lexiconName: CSV_NAME, lexiconMtime: "", lexiconSource: "repo",
    results: [], // { id, name, result, error, reportName }
  };

  const $ = sel => document.querySelector(sel);

  // ---------- 文字解碼：UTF-8（含 BOM）優先，失敗改 Big5 ----------
  function decodeText(buffer) {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    } catch (_) {
      try { return new TextDecoder("big5").decode(buffer); }
      catch (e) { throw new Error("檔案編碼無法辨識，請以 UTF-8 或 Big5 另存後重試。"); }
    }
  }

  // ---------- 詞庫載入 ----------
  async function loadLexiconFromRepo() {
    const res = await fetch(encodeURI(CSV_NAME) + "?t=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error(`找不到詞庫檔「${CSV_NAME}」（HTTP ${res.status}），請確認已放在網站根目錄。`);
    const buf = await res.arrayBuffer();
    const lm = res.headers.get("last-modified");
    applyLexicon(decodeText(buf), CSV_NAME, lm ? new Date(lm).toLocaleString("zh-TW") : "", "repo");
  }

  async function loadLexiconFromFile(file) {
    const buf = await file.arrayBuffer();
    applyLexicon(decodeText(buf), file.name, new Date(file.lastModified).toLocaleString("zh-TW"), "custom");
  }

  function applyLexicon(text, name, mtime, source) {
    const { rules, warnings } = M.loadRules(text);
    state.rules = rules; state.warnings = warnings; state.ruleCount = rules.length;
    state.lexiconName = name; state.lexiconMtime = mtime; state.lexiconSource = source;
    renderLexiconStatus();
  }

  function renderLexiconStatus() {
    const el = $("#lexicon-status");
    const src = state.lexiconSource === "custom" ? "（自訂詞庫，僅本次使用）" : "";
    el.innerHTML = `
      <span class="ok">✓</span> 詞庫 <strong>${esc(state.lexiconName)}</strong>${src}
      · ${state.ruleCount} 條規則${state.lexiconMtime ? " · 更新於 " + esc(state.lexiconMtime) : ""}
      ${state.warnings.map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}`;
    el.className = "status";
    $("#run-paste").disabled = false;
  }

  // ---------- 檔案讀取層：統一輸出 [[位置字串, 文字], ...] ----------
  function readTxt(text) {
    const units = [];
    text.split("\n").forEach((line, i) => {
      line = line.replace(/\r$/, "");
      if (line.trim()) units.push([`第 ${i + 1} 行`, line]);
    });
    return units;
  }

  function readCsv(text) {
    const units = [];
    M.parseCsv(text).forEach((row, r) => {
      row.forEach((cell, c) => {
        if (cell.trim()) units.push([`第 ${r + 1} 列第 ${c + 1} 欄`, cell]);
      });
    });
    return units;
  }

  function cellText(cell) {
    const v = cell.value;
    if (v == null) return "";
    if (typeof v === "string") return v;
    if (typeof v === "object") {
      if (Array.isArray(v.richText)) return v.richText.map(t => t.text).join("");
      if (typeof v.text === "string") return v.text;                 // hyperlink
      if (typeof v.result === "string") return v.result;             // formula
    }
    return ""; // 數字、日期、布林等非字串型儲存格跳過
  }

  async function readXlsx(buffer) {
    if (!window.ExcelJS) throw new Error("Excel 讀取元件尚未載入，請重新整理頁面。");
    const wb = new ExcelJS.Workbook();
    try { await wb.xlsx.load(buffer); }
    catch (e) { throw new Error("無法開啟 Excel 檔案，請確認檔案未損毀且非加密檔。"); }
    const units = [];
    wb.eachSheet(ws => {
      ws.eachRow(row => {
        row.eachCell(cell => {
          const t = cellText(cell);
          if (t.trim()) units.push([`${ws.name}!${cell.address}`, t]);
        });
      });
    });
    return units;
  }

  async function readFile(file) {
    const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    if (!SUPPORTED.includes(ext)) {
      throw new Error(`不支援的檔案格式「${ext || "（無副檔名）"}」，僅支援：${SUPPORTED.join("、")}`);
    }
    const buf = await file.arrayBuffer();
    if (ext === ".xlsx") return readXlsx(buf);
    const text = decodeText(buf);
    return ext === ".txt" ? readTxt(text) : readCsv(text);
  }

  // ---------- 檢查 ----------
  function selectedLevels() {
    return M.ALL_LEVELS.filter(lv => $(`#level-${lv}`).checked);
  }

  function stamp(d) {
    const p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  }

  async function checkFiles(files) {
    if (!state.rules.length) { alert("詞庫尚未載入，請稍候再試。"); return; }
    const levels = selectedLevels();
    if (!levels.length) { alert("請至少勾選一個檢查等級。"); return; }
    for (const file of files) {
      const entry = { id: Date.now() + Math.random(), name: file.name, at: new Date() };
      try {
        const units = await readFile(file);
        entry.result = M.checkUnits(units, state.rules, levels);
      } catch (e) {
        entry.error = e.message || String(e);
      }
      state.results.unshift(entry);
    }
    renderResults();
  }

  function checkPastedText() {
    const text = $("#paste-text").value;
    if (!text.trim()) return;
    const levels = selectedLevels();
    if (!levels.length) { alert("請至少勾選一個檢查等級。"); return; }
    const entry = { id: Date.now(), name: "貼上的文字", at: new Date(), pasted: true };
    entry.result = M.checkUnits(readTxt(text), state.rules, levels);
    state.results.unshift(entry);
    renderResults();
  }

  // ---------- Excel 報告（總覽＋明細） ----------
  const FILLS = { "高": "FFFFC7CE", "中": "FFFFD8A8", "低": "FFC6EFCE" };
  const FONTS = { "高": "FF9C0006", "中": "FF974E00", "低": "FF006100" };

  async function buildReportBuffer(entry) {
    const r = entry.result;
    const wb = new ExcelJS.Workbook();
    const ov = wb.addWorksheet("總覽");
    ov.columns = [{ width: 24 }, { width: 48 }];
    const rows = [
      ["受檢檔名", entry.name],
      ["檢查時間", entry.at.toLocaleString("zh-TW")],
      ["詞庫檔名", state.lexiconName],
      ["詞庫最後修改時間", state.lexiconMtime || "（無法取得）"],
      ["詞庫規則數", state.ruleCount],
      ["檢查等級設定", M.ALL_LEVELS.filter(lv => r.levels.includes(lv)).join("＋")],
      ["掃描單元數", r.totalUnits],
      ["通過數", r.passedUnits],
      ["未通過數", r.failedUnits],
      ["高風險命中數", r.hitsByRisk["高"] || 0],
      ["中風險命中數", r.hitsByRisk["中"] || 0],
      ["低風險命中數（僅供參考）", r.hitsByRisk["低"] || 0],
      ...state.warnings.map(w => ["詞庫提醒", w]),
    ];
    rows.forEach(([k, v]) => { const row = ov.addRow([k, v]); row.getCell(1).font = { bold: true }; });

    const dt = wb.addWorksheet("明細");
    dt.columns = [16, 12, 18, 10, 48, 12, 30].map(w => ({ width: w }));
    const header = dt.addRow(["位置", "命中詞", "修改建議", "風險等級", "前後文", "類別", "備註"]);
    header.eachCell(c => { c.font = { bold: true }; c.alignment = { horizontal: "center" }; });
    for (const { position, hit } of r.unitHits) {
      const row = dt.addRow([position, hit.term, hit.suggestion, hit.risk, hit.context, hit.category, hit.note]);
      const rc = row.getCell(4);
      if (FILLS[hit.risk]) {
        rc.fill = { type: "pattern", pattern: "solid", fgColor: { argb: FILLS[hit.risk] } };
        rc.font = { color: { argb: FONTS[hit.risk] } };
      }
    }
    dt.views = [{ state: "frozen", ySplit: 1 }];
    dt.autoFilter = `A1:G${Math.max(2, r.unitHits.length + 1)}`;
    return wb.xlsx.writeBuffer();
  }

  async function downloadReport(entry) {
    const buf = await buildReportBuffer(entry);
    const stem = entry.name.replace(/\.[^.]+$/, "");
    const name = `${stem}_檢查報告_${stamp(entry.at)}.xlsx`;
    const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  }

  // ---------- 畫面 ----------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function contextHtml(ctx) {
    return esc(ctx).replace(/【(.+?)】/, '<mark>$1</mark>');
  }

  function renderResults() {
    const wrap = $("#results");
    if (!state.results.length) { wrap.innerHTML = ""; return; }
    wrap.innerHTML = state.results.map(e => {
      if (e.error) {
        return `<section class="card error"><h3>✗ ${esc(e.name)}</h3><p>${esc(e.error)}</p></section>`;
      }
      const r = e.result;
      const pass = r.failedUnits === 0;
      const rows = r.unitHits.map(({ position, hit }) => `
        <tr>
          <td class="pos">${esc(position)}</td>
          <td><strong>${esc(hit.term)}</strong></td>
          <td>${esc(hit.suggestion)}</td>
          <td><span class="risk risk-${esc(hit.risk)}">${esc(hit.risk)}</span></td>
          <td class="ctx">${contextHtml(hit.context)}</td>
          <td>${esc(hit.category)}</td>
          <td class="note">${esc(hit.note)}</td>
        </tr>`).join("");
      return `
        <section class="card ${pass ? "pass" : "fail"}">
          <header>
            <h3>${pass ? "✅" : "⚠️"} ${esc(e.name)}</h3>
            <div class="actions">
              ${e.pasted ? "" : `<button data-dl="${e.id}">下載 Excel 報告</button>`}
              <button class="ghost" data-rm="${e.id}">移除</button>
            </div>
          </header>
          <p class="summary">
            掃描 <b>${r.totalUnits}</b> 處 · 通過 <b>${r.passedUnits}</b> 處 ·
            發現 <b>${r.totalHits}</b> 處建議修改
            <span class="dim">（高 ${r.hitsByRisk["高"] || 0}／中 ${r.hitsByRisk["中"] || 0}／低 ${r.hitsByRisk["低"] || 0}）</span>
          </p>
          ${r.unitHits.length ? `
          <div class="table-wrap"><table>
            <thead><tr><th>位置</th><th>命中詞</th><th>修改建議</th><th>風險</th><th>前後文</th><th>類別</th><th>備註</th></tr></thead>
            <tbody>${rows}</tbody>
          </table></div>` : `<p class="dim">沒有發現需要修改的用語。</p>`}
        </section>`;
    }).join("");
  }

  // ---------- 事件 ----------
  function bind() {
    const drop = $("#drop");
    const input = $("#file-input");
    ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => checkFiles([...e.dataTransfer.files]));
    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    input.addEventListener("change", () => { checkFiles([...input.files]); input.value = ""; });

    $("#run-paste").addEventListener("click", checkPastedText);
    $("#clear").addEventListener("click", () => { state.results = []; renderResults(); });

    $("#custom-lexicon").addEventListener("change", async e => {
      const f = e.target.files[0];
      if (!f) return;
      try { await loadLexiconFromFile(f); }
      catch (err) { alert("自訂詞庫載入失敗：" + err.message); }
      e.target.value = "";
    });
    $("#reset-lexicon").addEventListener("click", () => loadLexiconFromRepo().catch(showLexiconError));

    $("#results").addEventListener("click", e => {
      const dl = e.target.closest("[data-dl]");
      const rm = e.target.closest("[data-rm]");
      if (dl) {
        const entry = state.results.find(x => String(x.id) === dl.dataset.dl);
        if (entry) downloadReport(entry).catch(err => alert("報告產生失敗：" + err.message));
      } else if (rm) {
        state.results = state.results.filter(x => String(x.id) !== rm.dataset.rm);
        renderResults();
      }
    });
  }

  function showLexiconError(err) {
    const el = $("#lexicon-status");
    el.className = "status error";
    el.innerHTML = `<span>✗</span> ${esc(err.message)}`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    bind();
    loadLexiconFromRepo().catch(showLexiconError);
  });

  // 供測試與除錯使用
  window.App = { readFile, readTxt, readCsv, checkFiles, buildReportBuffer, state, decodeText };
})();
