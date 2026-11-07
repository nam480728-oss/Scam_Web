/* Bảng điều khiển Vệ sĩ: ô thống kê, biểu đồ (CSS + canvas), dòng thời gian thời gian thực */
(function () {
  "use strict";
  const SC = window.SC; const page = document.getElementById("gd-page"); if (!SC || !page) return;
  const { el, api } = SC;
  const $ = (id) => document.getElementById(id);
  let stats = null, events = [];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function tile(label, value, sub, icon) {
    const t = el("div", "card tile"); t.append(el("div", "tile-ico", icon), el("div", "tile-val", String(value)), el("div", "tile-lbl", label));
    if (sub) t.appendChild(el("div", "tile-sub", sub)); return t;
  }
  function renderStats() {
    const s = stats, k = s.by_kind || {}, ap = s.appeals || {}, lb = s.labels || {};
    $("gd-tiles").replaceChildren(
      tile("Tin nhắn đã đọc", s.messages, `${k.ask || 0} lượt Hỏi Vệ sĩ`, "💬"),
      tile("Tin bị gắn cờ lừa đảo", s.flagged, s.messages ? `${Math.round(100 * s.flagged / s.messages)}% số tin` : "", "⚠️"),
      tile("Tự động chặn (lần 3)", s.auto_blocks, "đang bị chặn", "⛔"),
      tile("Khiếu nại gỡ chặn", Object.values(ap).reduce((a, b) => a + b, 0), `${ap.success || 0} thành công · ${ap.failed || 0} thất bại · ${ap.open || 0} đang mở`, "🧾"),
      tile("Nhãn từ người dùng", (lb.scam || 0) + (lb.not_scam || 0) + (lb.acquaintance || 0), `${lb.scam || 0} báo lừa đảo · ${(lb.not_scam || 0) + (lb.acquaintance || 0)} báo nhầm`, "🏷️"),
      tile("AI 3 trung bình", s.agent3_avg_ms != null ? s.agent3_avg_ms + " ms" : "–", s.modes.agent3_model || "", "⚡"));
    const m = s.modes;
    $("gd-modes").replaceChildren(el("span", "pill", `📖 AI 3: ${m.agent3}${m.agent3_model ? " · " + m.agent3_model : ""}`), el("span", "pill", "⚖️ Luật 3 lần"));
    renderLevels(); drawHourly();
  }

  // Bar ngang theo mức cảnh báo - màu trạng thái dành riêng, luôn kèm biểu tượng + nhãn
  function renderLevels() {
    const box = $("gd-levels"); box.replaceChildren();
    const bl = stats.by_level || {}; const vals = [0, 1, 2, 3].map((l) => bl[String(l)] || 0); const max = Math.max(1, ...vals);
    vals.forEach((v, l) => {
      const [ico, name] = SC.pipe.LEVEL[l];
      const row = el("div", "lv-row"); row.title = `${name}: ${v} tin nhắn`;
      const track = el("div", "lv-track"); const bar = el("div", "lv-bar lv" + l); bar.style.width = (v / max * 100) + "%"; track.appendChild(bar);
      row.append(el("span", "lv-name", `${ico} ${name}`), track, el("b", "lv-num", String(v))); box.appendChild(row);
    });
  }

  // Cột theo giờ trên canvas: 1 chuỗi, 1 màu, đầu cột bo 4px, lưới nhạt, tooltip khi rê chuột
  let bars = [];
  function drawHourly() {
    const cv = $("gd-hourly"), data = stats.hourly || [], dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth || 500, h = 180; cv.width = w * dpr; cv.height = h * dpr;
    const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
    const pad = { l: 30, r: 8, t: 10, b: 22 }, max = Math.max(1, ...data), ih = h - pad.t - pad.b, iw = w - pad.l - pad.r;
    g.font = "11px system-ui, sans-serif"; g.fillStyle = css("--muted"); g.strokeStyle = css("--line"); g.lineWidth = 1;
    const ticks = max <= 4 ? max : 4;
    for (let i = 0; i <= ticks; i++) {
      const y = pad.t + ih - (i / ticks) * ih; g.globalAlpha = 0.6; g.beginPath(); g.moveTo(pad.l, y); g.lineTo(w - pad.r, y); g.stroke(); g.globalAlpha = 1;
      g.fillText(String(Math.round(max * i / ticks)), 4, y + 4);
    }
    const bw = iw / 24, now = new Date(); bars = [];
    data.forEach((v, i) => {
      const x = pad.l + i * bw + 2, bh = v / max * ih, y = pad.t + ih - bh, ww = Math.max(2, bw - 4);
      g.fillStyle = css("--primary");
      if (bh > 0) { const r = Math.min(4, ww / 2, bh); g.beginPath(); g.moveTo(x, pad.t + ih); g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.lineTo(x + ww - r, y); g.quadraticCurveTo(x + ww, y, x + ww, y + r); g.lineTo(x + ww, pad.t + ih); g.fill(); }
      const hour = new Date(now - (23 - i) * 3600e3).getHours();
      if (i % 4 === 3) { g.fillStyle = css("--muted"); g.fillText(`${hour}h`, x, h - 6); }
      bars.push({ x: pad.l + i * bw, w: bw, v, hour });
    });
    const tb = $("gd-hourly-table"); const t = el("table", "mini-table"); const tr1 = el("tr"), tr2 = el("tr");
    bars.forEach((b) => { tr1.appendChild(el("th", null, b.hour + "h")); tr2.appendChild(el("td", null, String(b.v))); }); t.append(tr1, tr2); tb.replaceChildren(t);
  }
  $("gd-hourly").addEventListener("mousemove", (e) => {
    const r = e.target.getBoundingClientRect(), x = e.clientX - r.left, b = bars.find((q) => x >= q.x && x < q.x + q.w), tip = $("gd-tip");
    if (!b) { tip.classList.add("hidden"); return; }
    tip.textContent = `${b.hour}:00 – ${b.hour}:59 · ${b.v} sự kiện`; tip.style.left = Math.min(r.width - 150, b.x) + "px"; tip.classList.remove("hidden");
  });
  $("gd-hourly").addEventListener("mouseleave", () => $("gd-tip").classList.add("hidden"));
  window.addEventListener("resize", () => stats && drawHourly());
  new MutationObserver(() => stats && drawHourly()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  // ---- dòng thời gian ----
  function renderTimeline() {
    const f = $("gd-filter").value, box = $("gd-timeline"); box.replaceChildren();
    const list = events.filter((e) => !f || e.kind === f);
    if (!list.length) box.appendChild(el("div", "empty", "Chưa có sự kiện nào. Hãy nhắn tin hoặc mở trang Demo để phát kịch bản."));
    list.slice(0, 80).forEach((e) => box.appendChild(SC.pipe.eventRow(e)));
  }
  $("gd-filter").addEventListener("change", renderTimeline);

  const load = async () => {
    const [s, ev] = await Promise.all([api("GET", "/api/guardian/stats"), api("GET", "/api/guardian/events?limit=80")]);
    stats = s; events = ev.events; renderStats(); renderTimeline();
  };
  let reloadT = null;
  const softReload = () => { clearTimeout(reloadT); reloadT = setTimeout(async () => { try { stats = await api("GET", "/api/guardian/stats", null, { silent: true }); renderStats(); } catch (e) { /* bỏ qua */ } }, 400); };
  if (SC.socket) {
    const join = () => SC.socket.emit("guardian:join", {});
    SC.socket.on("connect", join); if (SC.socket.connected) join();
    SC.socket.on("guardian:event", (e) => {
      events = [e, ...events.filter((x) => x.id !== e.id)].slice(0, 200); renderTimeline(); softReload();
      const first = $("gd-timeline").firstElementChild; if (first && first.dataset.id == e.id) first.classList.add("flash");
    });
  }
  load();
})();
