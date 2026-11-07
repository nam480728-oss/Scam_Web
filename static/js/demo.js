/* Màn hình trình diễn: phát kịch bản (máy chủ gửi tin nhắn cách nhau 2-3 giây),
   3 cột: kẻ gian | nạn nhân | dây chuyền Vệ sĩ (tiền xử lý → AI 3 → luật 3 lần) sáng lần lượt; công tắc bật/tắt AI 3 của nạn nhân. */
(function () {
  "use strict";
  const SC = window.SC; const page = document.getElementById("demo-page"); if (!SC || !page) return;
  const { el, api, toast } = SC;
  const $ = (id) => document.getElementById(id);
  let scenarios = [], cur = null, playing = false;
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };

  /* ------------------------------------------------------------ chọn kịch bản */
  function pick(id) {
    cur = scenarios.find((s) => s.id === id) || scenarios[0]; if (!cur) return;
    const info = $("demo-info"); info.replaceChildren();
    info.append(el("h2", null, `Kịch bản ${cur.no}: ${cur.title}`), el("p", null, cur.summary));
    if (cur.expect) info.appendChild(el("p", "expect", "🎯 Kỳ vọng: " + cur.expect));
    const ol = el("ol", "demo-steps"); cur.steps.forEach((s, i) => { const li = el("li", null, stepText(s)); li.dataset.i = i; ol.appendChild(li); }); info.appendChild(ol);
    $("demo-victim-name").textContent = cur.victim ? "· " + cur.victim.name : "";
    $("demo-scammer-name").textContent = cur.scammers.length ? "· " + cur.scammers.map((s) => s.name).join(", ") : "· (không có kẻ gian)";
    page.querySelectorAll("#demo-toggles .switch").forEach((s) => { s.checked = !!(cur.victim && cur.victim.agents[s.dataset.agent]); });
    clearCols();
  }
  function stepText(s) {
    const T = { message: `💬 ${s.from}: “${s.text}”`, file: `📦 ${s.from} gửi tệp ${s.file}${s.text ? ` – “${s.text}”` : ""}`,
      broadcast: `📨 ${s.from} rải tin cho ${s.count} người lạ: “${s.text}”`, report: `🚩 ${s.from} bấm “Báo cáo lừa đảo” ${s.to}` };
    return (s.label ? s.label + " — " : "") + (T[s.type] || s.type);
  }
  function clearCols() {
    $("col-scammer").replaceChildren(el("div", "phone-empty", "Bấm ▶ Phát kịch bản"));
    $("col-victim").replaceChildren(el("div", "phone-empty", "Màn hình của nạn nhân"));
    $("demo-events").replaceChildren();
    page.querySelectorAll(".stage").forEach((s) => { s.className = "stage"; s.querySelector("em").textContent = ""; });
  }
  const addTo = (id, node) => { const b = $(id); const e = b.querySelector(".phone-empty"); if (e) e.remove(); b.appendChild(node); b.scrollTop = b.scrollHeight; return node; };

  /* ------------------------------------------------------------ cột kẻ gian */
  function scammerStep(p) {
    const s = p.step;
    if (p.status === "running") {
      if (s.type === "message" || s.type === "file") {
        const b = el("div", "pb mine"); if (s.days_ago) b.appendChild(el("small", "pb-day", `${s.days_ago} ngày trước`));
        if (s.type === "file") b.appendChild(el("div", "pb-file", "📦 " + s.file));
        if (s.text) b.appendChild(el("div", null, s.text)); b.appendChild(el("small", "pb-st", "✓ Đã gửi")); addTo("col-scammer", b);
      } else if (s.type === "broadcast") addTo("col-scammer", el("div", "pb mine", `📨 Đang gửi cho ${s.count} người: “${s.text}”`));
      else if (s.type === "report") addTo("col-victim", el("div", "pb sys", `🚩 ${s.from} bấm “Báo cáo lừa đảo”`));
    } else if (p.status === "done") {
      if (s.type === "broadcast") addTo("col-scammer", el("div", "pb sys", `✓ Đã gửi ${p.result.sent} tin`));
      if (s.type === "report" && p.result) addTo("col-victim", el("div", "pb herd", "🏷️ Đã lưu báo cáo làm nhãn “lừa đảo” để train mô hình kịch bản"));
    }
  }

  /* ------------------------------------------------------------ cột nạn nhân */
  const LV = { 0: "", 1: "l1", 2: "l2", 3: "l3" };
  function victimEvent(ev) {
    const r = ev.results || {};
    if (ev.kind === "message") {
      const a3 = r.agent3 || {}, d = r.decision || {}, act = d.actions || {};
      const wrap = el("div", "pb other " + LV[ev.level]);
      if (act.mask) { wrap.appendChild(el("b", null, "🛡️ Vệ sĩ đã che tin nhắn nguy hiểm")); const s = el("details", "small"); s.append(el("summary", null, "Xem nội dung"), el("div", null, ev.text || "")); wrap.appendChild(s); }
      else wrap.appendChild(el("div", null, ev.text || ""));
      addTo("col-victim", wrap);
      if (ev.level >= 1) {
        const c = el("div", "guard-card " + LV[ev.level]); const h = el("div", "gc-head");
        h.append(SC.pipe.levelBadge(ev.level)); if (a3.scenario && a3.scenario !== "none") h.appendChild(el("span", "pill danger", a3.scenario_label || a3.scenario));
        if (a3.phase && a3.phase !== "none") h.appendChild(el("span", "pill", "Pha: " + (a3.phase_label || a3.phase)));
        c.appendChild(h); if (a3.explanation_vi) c.appendChild(el("p", "gc-text", a3.explanation_vi));
        const ul = el("ul", "gc-signals"); (a3.signals || []).slice(0, 4).forEach((s) => ul.appendChild(el("li", null, s))); c.appendChild(ul);
        if (act.family_hint) c.appendChild(el("div", "family-box", "👨‍👩‍👧 Gợi ý: hỏi Mật mã gia đình trước khi chuyển tiền"));
        if (act.block_apk) c.appendChild(el("div", "gc-apk", "📦 Tệp cài đặt đã bị chặn tải xuống"));
        if (act.confirm_apk) c.appendChild(el("div", "small", "📦 Tải tệp APK phải xác nhận lại (lần 2 sẽ chặn tải)"));
        if (act.copy_delay) c.appendChild(el("div", "small", "⏳ Sao chép STK phải chờ đếm ngược 60 giây"));
        if (act.blur_links) c.appendChild(el("div", "small", "🔒 Link trong tin bị làm mờ"));
        addTo("col-victim", c);
        if (act.block_sender) {
          addTo("col-victim", el("div", "pb cut", "⛔ Lần 3: Vệ sĩ đã TỰ ĐỘNG CHẶN người gửi · có nút “Khiếu nại gỡ chặn”"));
          addTo("col-scammer", el("div", "pb cut", "⛔ Bạn đã bị hệ thống chặn nhắn tin (phát hiện lừa đảo 3 lần) · có nút “Khiếu nại”"));
        }
      } else addTo("col-victim", el("div", "ok-tag", "✅ An toàn"));
    }
  }
  /* ------------------------------------------------------------ cột dây chuyền */
  function lightStage(stage, status, summary) {
    const s = page.querySelector(`.stage[data-stage="${stage}"]`); if (!s) return;
    s.className = "stage " + status; if (summary != null) s.querySelector("em").textContent = summary;
  }
  const ORDER = ["text", "agent3", "decision"];
  function onStage(p) {
    if (p.stage === "start") { ORDER.forEach((x) => lightStage(x, "", "")); return; }
    if (p.status === "running") lightStage(p.stage, "running", "Đang xử lý…");
    else lightStage(p.stage, p.stage === "decision" ? ("lv lv" + (p.level || 0)) : "done", p.summary);
  }

  /* ------------------------------------------------------------ socket */
  if (SC.socket) {
    const join = () => SC.socket.emit("guardian:join", {}); SC.socket.on("connect", join); if (SC.socket.connected) join();
    SC.socket.on("guardian:stage", onStage);
    SC.socket.on("guardian:event", (ev) => {
      const evs = $("demo-events"); evs.prepend(SC.pipe.eventRow(ev)); while (evs.children.length > 6) evs.lastChild.remove();
      if (cur && cur.victim && ev.protected_id === cur.victim.id) victimEvent(ev);
    });
    SC.socket.on("demo:step", (p) => {
      if (!cur || p.scenario !== cur.id) return;
      page.querySelectorAll(".demo-steps li").forEach((li) => li.classList.toggle("now", +li.dataset.i === p.index && p.status === "running"));
      const li = page.querySelector(`.demo-steps li[data-i="${p.index}"]`); if (li && p.status === "done") li.classList.add("done");
      scammerStep(p);
    });
    SC.socket.on("demo:done", (p) => { playing = false; $("demo-play").disabled = false; $("demo-play").textContent = "▶ Phát kịch bản"; if (p.error) toast("Lỗi kịch bản: " + p.error, "error"); else toast("Kịch bản đã phát xong", "ok"); });
  }

  /* ------------------------------------------------------------ điều khiển */
  $("demo-scenario").addEventListener("change", (e) => pick(e.target.value));
  $("demo-play").addEventListener("click", guard(async () => {
    if (!cur || playing) return;
    clearCols(); playing = true; $("demo-play").disabled = true; $("demo-play").textContent = "⏳ Đang phát…";
    try { await api("POST", `/api/demo/play/${cur.id}`, { delay: parseFloat($("demo-delay").value) }); }
    catch (e) { playing = false; $("demo-play").disabled = false; $("demo-play").textContent = "▶ Phát kịch bản"; throw e; }
  }));
  $("demo-reset").addEventListener("click", guard(async () => {
    if (!cur) return;
    await api("POST", `/api/demo/reset/${cur.id}`); clearCols(); toast("Đã làm mới dữ liệu kịch bản", "ok");
  }));
  page.querySelectorAll("#demo-toggles .switch").forEach((s) => s.addEventListener("change", guard(async () => {
    if (!cur) return;
    const r = await api("POST", `/api/demo/agents/${cur.id}`, { [s.dataset.agent]: s.checked });
    cur.victim.agents = r.agents;
    toast(`${s.checked ? "Bật" : "Tắt"} ${s.parentElement.textContent.trim()} của ${cur.victim.name}`, s.checked ? "ok" : "");
  })));

  guard(async () => {
    const d = await api("GET", "/api/demo/scenarios");
    if (!d.seeded) { $("demo-info").replaceChildren(el("div", "notice warn", "Chưa có dữ liệu demo cho mô hình này. Chạy “python seed.py” rồi tải lại trang.")); $("demo-play").disabled = true; return; }
    scenarios = d.scenarios;
    const sel = $("demo-scenario"); scenarios.forEach((s) => { const o = el("option", null, `${s.no}. ${s.title}`); o.value = s.id; sel.appendChild(o); });
    pick(scenarios[0].id);
  })();
})();
