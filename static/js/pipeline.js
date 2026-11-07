/* Dựng giao diện một sự kiện Vệ sĩ (dùng chung cho /guardian và /demo): 3 cột Tiền xử lý | AI 3 | Quyết định (luật 3 lần),
   mỗi cột ghi thời gian xử lý (ms) và chế độ (luật / model / mock). */
(function () {
  "use strict";
  const SC = window.SC; if (!SC) return;
  const { el } = SC;
  const KIND = { message: ["💬", "Tin nhắn"], ask: ["🛡️", "Hỏi Vệ sĩ"], appeal: ["🧾", "Khiếu nại gỡ chặn"] };
  const LEVEL = { 0: ["✅", "An toàn"], 1: ["⚠️", "Lần 1 · Cảnh báo"], 2: ["🚨", "Lần 2 · Che tin"], 3: ["⛔", "Lần 3 · Tự chặn"] };

  function levelBadge(l) { const [i, t] = LEVEL[l] || LEVEL[0]; return el("span", "lv-badge lv" + (l || 0), `${i} ${t}`); }
  // Tô sáng phần văn bản đã được chuẩn hóa (teencode, chữ chèn ký tự) - dựng bằng DOM, không dùng innerHTML
  function highlight(text, changes) {
    const box = el("div", "norm-text");
    const targets = [...new Set((changes || []).map((c) => c.to))].filter(Boolean).sort((a, b) => b.length - a.length);
    if (!targets.length) { box.textContent = text; return box; }
    const re = new RegExp(targets.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) box.appendChild(document.createTextNode(text.slice(last, m.index)));
      const mk = el("mark", null, m[0]); const ch = changes.find((c) => c.to === m[0]); if (ch) mk.title = `Gốc: “${ch.from}”`; box.appendChild(mk);
      last = m.index + m[0].length; if (!m[0].length) re.lastIndex++;
    }
    if (last < text.length) box.appendChild(document.createTextNode(text.slice(last)));
    return box;
  }
  const chip = (t, cls) => el("span", "ent " + (cls || ""), t);
  function col(title, mode, ms) {
    const c = el("div", "pcol"); const h = el("div", "pcol-h");
    h.append(el("b", null, title), el("span", "pcol-meta", `${mode || "–"} · ${ms != null ? Math.round(ms * 10) / 10 + " ms" : "–"}`));
    c.appendChild(h); return c;
  }

  function textCol(tx, ms) {
    const c = col("🔤 Tiền xử lý", "luật", ms);
    if (!tx) { c.appendChild(el("div", "muted small", "Không có chữ để đọc")); return c; }
    if (tx.normalized_text) c.appendChild(highlight(tx.normalized_text, tx.changes));
    const ents = el("div", "ents");
    (tx.bank_accounts || []).forEach((x) => ents.appendChild(chip("🏦 " + x)));
    (tx.urls || []).forEach((u) => ents.appendChild(chip("🔗 " + u.domain)));
    (tx.amounts || []).slice(0, 3).forEach((x) => ents.appendChild(chip("💵 " + x.toLocaleString("vi-VN") + "đ", "soft")));
    if (ents.childNodes.length) c.appendChild(ents);
    const kw = Object.keys(tx.keywords || {}); if (kw.length) c.appendChild(el("div", "muted small", "Từ khóa: " + kw.join(", ")));
    return c;
  }
  function agent3Col(a3, ms, mode) {
    const c = col("📖 AI 3 · Đọc vị", mode, ms);
    if (!a3) { c.appendChild(el("div", "muted small", "Không chạy")); return c; }
    const risk = a3.risk_score || 0;
    const bar = el("div", "risk-bar"); const f = el("i"); f.style.width = Math.round(risk * 100) + "%"; f.className = risk >= 0.85 ? "r3" : risk >= 0.6 ? "r2" : risk >= 0.35 ? "r1" : "r0";
    bar.appendChild(f); c.append(el("div", "small", `Rủi ro ${risk.toFixed(2)}${a3.model_prob != null ? ` · mô hình ${Number(a3.model_prob).toFixed(2)}` : ""}${a3.calibration && a3.calibration.factor != null ? ` ×${a3.calibration.factor}` : ""}`), bar);
    const tags = el("div", "ents");
    if (a3.scenario && a3.scenario !== "none") tags.appendChild(chip(a3.scenario_label || a3.scenario, "warn"));
    if (a3.phase && a3.phase !== "none") tags.appendChild(chip("Pha: " + (a3.phase_label || a3.phase), "soft"));
    if (tags.childNodes.length) c.appendChild(tags);
    if (a3.explanation_vi) c.appendChild(el("div", "small expl", a3.explanation_vi));
    if (a3.fallback_reason) c.appendChild(el("div", "bad small", "Dự phòng mock: " + a3.fallback_reason));
    return c;
  }
  function decisionCol(d, ev) {
    const c = col("⚖️ Quyết định", "luật 3 lần", ev.timings && ev.timings.decision);
    c.appendChild(levelBadge(ev.level));
    if (d) {
      if (d.counter_level) c.appendChild(el("div", "muted small", `Lần thứ ${d.counter_level} người này gửi tin lừa đảo`));
      const ul = el("ul", "small"); (d.reasons || []).forEach((x) => ul.appendChild(el("li", null, x))); c.appendChild(ul);
    }
    return c;
  }

  function eventRow(ev) {
    const r = ev.results || {}, t = ev.timings || {}, mo = ev.modes || {};
    const row = el("article", "pevent lvl" + (ev.level || 0)); row.dataset.kind = ev.kind; row.dataset.id = ev.id;
    const head = el("header", "pev-head");
    const [ico, name] = KIND[ev.kind] || ["•", ev.kind];
    head.append(el("span", "pev-kind", `${ico} ${name}`), el("span", "pev-who", `${ev.actor || "—"} → ${ev.protected || "—"}`), levelBadge(ev.level),
      el("time", null, `${new Date(ev.created_at).toLocaleTimeString("vi-VN")}${t.total != null ? " · " + t.total + " ms" : ""}`));
    row.appendChild(head);
    if (ev.text) row.appendChild(el("div", "pev-text", "“" + ev.text + "”"));
    const grid = el("div", "pgrid");
    if (ev.kind === "appeal") {
      const ap = r.appeal || {};
      const c = col("🧾 Khiếu nại", "chụp trực tiếp", null);
      c.appendChild(el("div", "small", `Bước: ${({ open: "mở khiếu nại", success: "THÀNH CÔNG – đã gỡ chặn, đếm lại từ lần 1", failed: "THẤT BẠI – giữ chặn" })[ap.stage] || ap.stage}`));
      if (ap.reason) c.appendChild(el("div", "bad", ap.reason));
      (ap.captures || []).forEach((x) => c.appendChild(el("div", "small", `${x.user === "protected" ? "Người được bảo vệ" : "Người bị chặn"}: `
        + `${x.passed ? "✓ đạt" : "✗ " + (x.reason || "")} · mặt ${x.faces}/3 · cử động ${x.motion}`)));
      if (ap.question_required) c.appendChild(el("div", "small", `Mật mã gia đình: ${ap.question_passed ? "✓ đúng" : "chưa đúng"}`));
      grid.appendChild(c); row.appendChild(grid);
      return row;
    }
    if (r.unreadable) {
      const c = col("🔇 Không đọc được", "–", null);
      c.appendChild(el("div", "small", ({ voice: "Tin nhắn thoại", image: "Ảnh không kèm chữ", file: "Tệp không kèm chữ" })[r.unreadable] || "Tin không có chữ"));
      grid.append(c, decisionCol(r.decision, ev));
    } else grid.append(textCol(r.text, t.text), agent3Col(r.agent3, t.agent3, mo.agent3), decisionCol(r.decision, ev));
    row.appendChild(grid);
    return row;
  }

  SC.pipe = { eventRow, levelBadge, highlight, KIND, LEVEL };
})();
