/* Giao diện bảo vệ dùng chung: banner người lạ, thẻ giải thích trên tin nhắn (AI 3), hãm thao tác
   (link mờ, đếm ngược 60 giây khi copy STK), Mật mã gia đình, "Vì sao?", Hỏi Vệ sĩ. */
(function () {
  "use strict";
  const SC = window.SC; if (!SC || !SC.me) return;
  const { el, api, toast } = SC;
  const G = SC.guard = {};
  const guardFn = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };
  const btn = (label, cls, fn) => { const b = el("button", "btn btn-sm " + (cls || ""), label); b.type = "button"; b.addEventListener("click", (e) => { e.stopPropagation(); fn(b); }); return b; };

  /* ================================================================ banner người lạ (đầu khung chat) */
  G.strangerBanner = function (slot, c) {
    const b = el("div", "stranger-banner chu_y"); slot.replaceChildren(b);
    const head = el("div", "sb-head");
    head.append(el("span", "sb-ico", "👤"), el("b", null, `${SC.displayName(c.other)} chưa là bạn bè của bạn`), el("span", "pill", `${c.mutual || 0} bạn chung`));
    if (c.request) head.appendChild(el("span", "pill warn", "Tin nhắn chờ"));
    if (c.reputation) head.appendChild(SC.repBadge(c.reputation));
    b.appendChild(head);
    if (c.reputation && c.reputation.level !== "green") b.appendChild(el("div", "sb-reason", `Độ uy tín: ${c.reputation.label}. ${c.reputation.hint}`));
    b.appendChild(el("div", "sb-reason", "Vệ sĩ đọc kỹ các tin của người lạ. Hãy thận trọng nếu được nhờ chuyển tiền, đọc mã OTP hay cài ứng dụng. Tin nhắn thoại không được kiểm tra."));
  };

  /* ================================================================ tin nhắn: thân tin có hãm thao tác */
  const URL_RE = /(https?:\/\/[^\s<]+|www\.[^\s<]+|\b(?:[a-z0-9-]+\.)+(?:com|vn|net|org|xyz|top|club|online|site|icu|vip|live|cc|me|io|shop|click|link|info|app|buzz)(?:\/[^\s<]*)?)/gi;
  // Dựng nội dung tin nhắn: link trong tin bị AI 3 gắn cờ thì làm mờ; STK có nút copy (lần 2+: đếm ngược 60 giây).
  G.renderBody = function (text, m, parent) {
    const g = m.guard || null;
    const accounts = (g && g.accounts) || [];
    let last = 0, mm; URL_RE.lastIndex = 0;
    while ((mm = URL_RE.exec(text))) {
      if (mm.index > last) appendWithAccounts(text.slice(last, mm.index), accounts, m, parent);
      parent.appendChild(!m.mine && g && g.blur_links ? blurredLink(mm[0]) : plainLink(mm[0]));
      last = mm.index + mm[0].length;
    }
    if (last < text.length) appendWithAccounts(text.slice(last), accounts, m, parent);
  };
  function plainLink(url) { const a = el("a", null, url); a.href = /^https?:/i.test(url) ? url : "https://" + url; a.target = "_blank"; a.rel = "noopener noreferrer nofollow"; return a; }
  function blurredLink(url) {
    const w = el("span", "blur-link"); w.appendChild(el("span", "bl-url", url));
    const reveal = el("button", "bl-btn", "🔒 Link nghi vấn · Tôi hiểu rủi ro, vẫn mở"); reveal.type = "button";
    reveal.title = "Vệ sĩ làm mờ link trong tin nhắn nghi lừa đảo";
    reveal.addEventListener("click", async (e) => {
      e.stopPropagation();
      const ok = await SC.dialog({ title: "Mở đường link nghi vấn?", icon: "🔗", danger: true, ok: "Tôi hiểu rủi ro, vẫn mở",
        text: "Link nằm trong tin nhắn có dấu hiệu lừa đảo. Trang giả mạo có thể lấy cắp mật khẩu, mã OTP hoặc cài phần mềm độc hại." });
      if (ok) w.replaceWith(plainLink(url));
    });
    w.appendChild(reveal); return w;
  }
  function appendWithAccounts(text, accounts, m, parent) {
    if (!accounts.length || m.mine) { parent.appendChild(document.createTextNode(text)); return; }
    const re = /\d[\d .-]{6,24}\d/g; let last = 0, mm;
    while ((mm = re.exec(text))) {
      const digits = mm[0].replace(/\D/g, "");
      if (!accounts.includes(digits)) continue;
      if (mm.index > last) parent.appendChild(document.createTextNode(text.slice(last, mm.index)));
      const chip = el("span", "acct"); chip.appendChild(document.createTextNode(mm[0]));
      const cp = el("button", "acct-copy", "📋"); cp.type = "button"; cp.title = "Sao chép số tài khoản";
      cp.addEventListener("click", (e) => { e.stopPropagation(); copyAccount(digits, m); });
      chip.appendChild(cp); parent.appendChild(chip); last = mm.index + mm[0].length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }
  async function copyAccount(digits, m) {
    const g = m.guard || {};
    if ((g.copy_delay || 0) > 0 && m.warning_level >= 2) { if (!(await countdownDialog(digits, g))) return; }
    try { await navigator.clipboard.writeText(digits); toast("Đã sao chép số tài khoản", "ok"); } catch (e) { toast("Không sao chép được.", "error"); }
  }
  // Hãm thao tác: đếm ngược 60 giây kèm câu hỏi tự kiểm tra trước khi cho copy STK
  function countdownDialog(digits, g) {
    return new Promise((resolve) => {
      const ov = el("div", "overlay"); const d = el("div", "dialog danger countdown");
      d.append(el("div", "big-icon", "⏳"), el("h3", null, "Chậm lại 60 giây trước khi chuyển tiền"));
      d.appendChild(el("p", null, `Bạn sắp sao chép số tài khoản ${digits}. Vệ sĩ đánh giá tin nhắn này có nguy cơ lừa đảo. Hãy tự trả lời:`));
      const qs = ["Tôi đã GỌI ĐIỆN (số quen thuộc) để xác minh người nhờ chuyển tiền", "Người này không dặn tôi giữ bí mật hay chuyển gấp",
        "Tôi biết rõ chủ tài khoản này là ai"];
      if (g.family_hint) qs.push("Người này đã trả lời đúng Mật mã gia đình");
      const list = el("div", "cd-checks");
      qs.forEach((q) => { const l = el("label", "check-row"); const c = el("input"); c.type = "checkbox"; l.append(c, el("span", null, q)); list.appendChild(l); });
      d.appendChild(list);
      const timer = el("div", "cd-timer", "60"); d.appendChild(timer);
      const a = el("div", "actions"); const no = el("button", "btn btn-primary", "Không chuyển nữa"); const ok = el("button", "btn btn-danger", "Sao chép (60)"); ok.disabled = true;
      a.append(no, ok); d.appendChild(a); ov.appendChild(d); document.body.appendChild(ov);
      let left = 60;
      const tick = () => {
        const allChecked = [...list.querySelectorAll("input")].every((c) => c.checked);
        timer.textContent = left > 0 ? String(left) : "✓"; timer.classList.toggle("done", left <= 0);
        ok.textContent = left > 0 ? `Sao chép (${left})` : "Sao chép";
        ok.disabled = left > 0 || !allChecked;
      };
      list.addEventListener("change", tick);
      const t = setInterval(() => { left -= 1; tick(); if (left <= 0) clearInterval(t); }, 1000);
      const done = (v) => { clearInterval(t); ov.remove(); resolve(v); };
      no.onclick = () => { done(false); toast("Rất tốt! Hãy gọi điện xác minh trước khi chuyển tiền.", "ok"); };
      ok.onclick = () => done(true);
      tick();
    });
  }

  /* ================================================================ thẻ giải thích dưới tin nhắn */
  const LV = { 1: { cls: "l1", ico: "⚠️", title: "Cảnh báo lần 1" }, 2: { cls: "l2", ico: "🚨", title: "Cảnh báo lần 2 · tin đã bị che" }, 3: { cls: "l3", ico: "⛔", title: "Lần 3 · Vệ sĩ đã tự động chặn" } };
  G.explainCard = function (m, conv, hooks = {}) {
    const g = m.guard; if (!g || m.mine || !m.warning_level) return null;
    const L = LV[Math.min(m.warning_level, 3)];
    const card = el("div", "guard-card " + L.cls);
    if (g.feedback) {
      card.classList.add("dismissed");
      card.append(el("span", null, { not_scam: "✓ Bạn đã đánh dấu: không phải lừa đảo", acquaintance: "✓ Bạn đã đánh dấu: người quen", scam: "✓ Bạn đã báo cáo lừa đảo" }[g.feedback] || "✓ Đã phản hồi"));
      return card;
    }
    const head = el("div", "gc-head"); head.append(el("span", "gc-ico", L.ico), el("b", null, g.unreadable ? "Người gửi đã bị cảnh báo · tin bị che" : L.title));
    if (g.scenario_label && g.scenario && g.scenario !== "none") head.appendChild(el("span", "pill " + (m.warning_level >= 2 ? "danger" : "warn"), g.scenario_label));
    if (g.phase_label && g.phase && g.phase !== "none") head.appendChild(el("span", "pill", "Pha: " + g.phase_label));
    card.appendChild(head);
    if (g.explanation) card.appendChild(el("p", "gc-text", g.explanation));
    if (g.signals && g.signals.length) { const ul = el("ul", "gc-signals"); g.signals.slice(0, 5).forEach((s) => ul.appendChild(el("li", null, s))); card.appendChild(ul); }
    const apk = m.attachment && m.attachment.is_apk;
    if (apk && !g.block_apk && m.warning_level === 1) card.appendChild(el("div", "gc-apk", "📦 Tệp cài đặt (.apk) trong tin này có thể là phần mềm độc hại. Đừng cài đặt; nếu thêm 1 lần lừa đảo nữa, Vệ sĩ sẽ chặn tải."));
    if (apk && g.block_apk) card.appendChild(el("div", "gc-apk", "📦 Tệp cài đặt đã bị chặn tải: cơ quan nhà nước, ngân hàng KHÔNG BAO GIỜ gửi ứng dụng qua tin nhắn."));
    if (g.family_hint) card.appendChild(familyBox(g, conv));
    const acts = el("div", "gc-actions");
    if (!g.unreadable) acts.appendChild(btn("❓ Vì sao?", "", () => whyDialog(m)));
    acts.append(btn("🚩 Báo cáo lừa đảo", "btn-danger", guardFn(async () => {
        if (!(await SC.dialog({ title: "Báo cáo lừa đảo?", icon: "🚩", danger: true, ok: "Báo cáo",
          text: "Tin nhắn này được lưu lại làm dữ liệu giúp Vệ sĩ học nhận diện lừa đảo tốt hơn. Người gửi không biết ai báo cáo." }))) return;
        await api("POST", "/api/guardian/report", { message_id: m.id, reason: "Người dùng báo cáo lừa đảo" });
        g.feedback = "scam"; hooks.rerender && hooks.rerender(); toast("Đã báo cáo. Cảm ơn bạn!", "ok");
      })),
      btn("✓ Không phải lừa đảo", "", guardFn(async () => { await api("POST", "/api/guardian/feedback", { message_id: m.id, label: "not_scam" }); g.feedback = "not_scam"; hooks.rerender && hooks.rerender(); toast("Cảm ơn! Phản hồi giúp Vệ sĩ học tốt hơn.", "ok"); })),
      btn("🚫 Chặn", "", () => hooks.block && hooks.block()));
    if (!conv || !conv.is_friend) acts.appendChild(btn("👋 Đây là người quen", "", guardFn(async () => { await api("POST", "/api/guardian/feedback", { message_id: m.id, label: "acquaintance" }); g.feedback = "acquaintance"; hooks.rerender && hooks.rerender(); })));
    card.appendChild(acts);
    return card;
  };
  function familyBox(g, conv) {
    const box = el("div", "family-box");
    box.appendChild(el("b", null, "👨‍👩‍👧 Hỏi Mật mã gia đình"));
    box.appendChild(el("p", null, "Tin này giống kiểu kẻ gian giả làm người thân. Hãy gọi lại số quen thuộc hoặc hỏi câu bí mật trước khi chuyển tiền."));
    if (g.family_question) {
      box.appendChild(el("p", "fq", `“${g.family_question}”`));
      const row = el("div", "gc-actions");
      row.append(btn("💬 Gửi câu hỏi bí mật", "btn-primary", () => { const i = document.getElementById("input"); if (i) { i.value = `Trả lời giúp mình: ${g.family_question}`; i.dispatchEvent(new Event("input")); i.focus(); } }),
        btn("🔍 Kiểm tra câu trả lời", "", guardFn(async () => {
          const r = await api("POST", "/api/guardian/family-check", { conversation_id: conv.id });
          const T = { match: ["✅ Trả lời ĐÚNG Mật mã gia đình.", "ok"], mismatch: ["❌ Trả lời SAI Mật mã gia đình – rất có thể là kẻ gian!", "error"], waiting: ["Chưa có câu trả lời.", ""] };
          toast(...T[r.result]);
        })));
      box.appendChild(row);
    } else box.appendChild(el("p", "muted small", "Bạn chưa đặt Mật mã gia đình – vào Cài đặt để đặt câu hỏi bí mật với người thân."));
    return box;
  }
  const whyDialog = guardFn(async (m) => {
    const d = (await api("GET", `/api/guardian/messages/${m.id}`)).event;
    const r = d.results || {}, t = d.timings || {}, mo = d.modes || {};
    const body = el("div", "why-grid");
    const col = (title, mode, ms, rows) => { const c = el("div", "why-col"); const h = el("div", "why-h"); h.append(el("b", null, title), el("span", "pill", `${mode || "–"} · ${ms != null ? ms + " ms" : "–"}`)); c.appendChild(h); rows.filter(Boolean).forEach((x) => c.appendChild(typeof x === "string" ? el("div", "why-row", x) : x)); return c; };
    const tx = r.text || {};
    body.appendChild(col("🔤 Tiền xử lý", "luật", t.text, [
      tx.normalized_text ? `Chuẩn hóa: “${tx.normalized_text}”` : null,
      (tx.changes || []).length ? `Gỡ chữ lách luật: ${tx.changes.map((c) => `${c.from} → ${c.to}`).join(", ")}` : null,
      (tx.bank_accounts || []).length ? `STK: ${tx.bank_accounts.join(", ")}` : null,
      (tx.urls || []).length ? `Link: ${tx.urls.map((u) => u.domain).join(", ")}` : null,
      Object.keys(tx.keywords || {}).length ? `Từ khóa: ${Object.keys(tx.keywords).join(", ")}` : null]));
    const a3 = r.agent3 || {};
    body.appendChild(col("📖 AI 3 · Đọc vị", mo.agent3, t.agent3, [
      `Rủi ro: ${(a3.risk_score ?? 0).toFixed(2)}${a3.model_prob != null ? ` (mô hình ${a3.model_name || ""}: ${Number(a3.model_prob).toFixed(2)})` : ""}`,
      a3.calibration && a3.calibration.factor != null ? `Hiệu chỉnh ngữ cảnh ×${a3.calibration.factor}${a3.calibration.trusted ? " (bạn bè)" : ""}${a3.calibration.pressure ? " (có dấu hiệu gây áp lực)" : ""}` : null,
      `Kịch bản: ${a3.scenario_label || "–"} · Pha: ${a3.phase_label || "–"}`,
      a3.fallback_reason ? `⚠️ Backend lỗi, dùng dự phòng: ${a3.fallback_reason}` : null,
      a3.explanation_vi]));
    const dec = r.decision || {};
    body.appendChild(col("⚖️ Quyết định", "luật 3 lần", t.decision, [`Lần thứ ${dec.counter_level || 0} · mức hiển thị ${dec.level}`, ...(dec.reasons || []).map((x) => "• " + x)]));
    await SC.dialog({ title: "Vì sao Vệ sĩ cảnh báo tin này?", body, ok: "Đóng", single: true, wide: true });
  });

  /* ================================================================ Hỏi Vệ sĩ */
  G.askDialog = guardFn(async function (conversationId, otherName) {
    const box = el("div", "form-grid ask-box");
    let ta = null;
    if (!conversationId) {
      ta = el("textarea", "input"); ta.rows = 5; ta.maxLength = 3000; ta.placeholder = "Dán tin nhắn bạn nghi ngờ vào đây (ví dụ tin nhắn SMS, Zalo…)";
      box.append(el("p", "muted small", "Vệ sĩ dùng AI 3 đọc đoạn tin rồi trả lời bằng tiếng Việt. Nội dung chỉ dùng để kiểm tra."), ta);
    } else box.appendChild(el("p", null, `Kiểm tra tin gần nhất của ${otherName} (kèm ngữ cảnh cuộc trò chuyện)?`));
    if (!(await SC.dialog({ title: "🛡️ Hỏi Vệ sĩ", body: box, ok: "Kiểm tra" }))) return;
    const r = await api("POST", "/api/guardian/ask", conversationId ? { conversation_id: conversationId } : { text: ta.value });
    const out = el("div", "ask-result l" + (r.level || 0));
    out.appendChild(el("div", "ask-verdict", r.verdict || ""));
    if (r.answer) out.appendChild(el("p", null, r.answer));
    if (r.scenario && r.level) out.appendChild(el("p", "muted small", `Kịch bản: ${r.scenario}${r.phase ? " · Pha: " + r.phase : ""}${r.risk != null ? " · Rủi ro " + r.risk.toFixed(2) : ""}`));
    if ((r.signals || []).length) { const ul = el("ul", "gc-signals"); r.signals.slice(0, 6).forEach((s) => ul.appendChild(el("li", null, s))); out.appendChild(ul); }
    if ((r.advice || []).length) { out.appendChild(el("b", null, "Lời khuyên:")); const ul = el("ul"); r.advice.forEach((s) => ul.appendChild(el("li", null, s))); out.appendChild(ul); }
    await SC.dialog({ title: "Vệ sĩ trả lời", body: out, ok: "Đã hiểu", single: true, wide: true });
  });
})();
