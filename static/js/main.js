/* Tiện ích dùng chung: gọi API, toast, hộp thoại, avatar, socket, thông báo, huy hiệu điều hướng, giao diện tối */
(function () {
  "use strict";
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const CFG = window.DANGNAM || {};

  async function api(method, url, body, opts = {}) {
    const init = { method, headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined && body !== null) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(url, init); } catch (e) { const err = new Error("Không kết nối được máy chủ."); err.network = true; throw err; }
    let data = null;
    try { data = await res.json(); } catch (e) { /* không phải JSON */ }
    if (!res.ok) {
      if (!opts.silent) {
        if (res.status === 401) { location.href = "/login"; }
        else if (res.status === 503 && data && data.code === "no_model") { location.href = "/"; }
      }
      const err = new Error((data && data.error) || `Lỗi ${res.status}`);
      err.status = res.status; err.code = data && data.code;
      throw err;
    }
    return data;
  }

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function toast(msg, type = "", opts = {}) {
    const box = document.getElementById("toasts");
    if (!box) return null;
    const t = el("div", "toast " + type);
    if (opts.icon) t.appendChild(el("span", "ticon", opts.icon));
    t.appendChild(el("span", "ttext", msg));
    if (opts.href) { t.classList.add("clickable"); t.addEventListener("click", () => { location.href = opts.href; }); }
    box.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, opts.ms || 4200);
    return t;
  }

  function dialog({ title, text, ok = "Đồng ý", cancel = "Hủy", danger = false, icon = "", single = false, key = "", body = null, wide = false }) {
    return new Promise((resolve) => {
      if (key && document.querySelector(`.overlay[data-key="${key}"]`)) { resolve(false); return; }   // không mở trùng
      const ov = el("div", "overlay"); if (key) ov.dataset.key = key;
      ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true");
      const d = el("div", "dialog" + (danger ? " danger" : "") + (wide ? " wide" : ""));
      if (icon) d.appendChild(el("div", "big-icon", icon));
      d.appendChild(el("h3", null, title));
      if (text) d.appendChild(el("p", null, text));
      if (body) d.appendChild(body);
      const a = el("div", "actions");
      const done = (v) => { ov.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
      if (!single) { const c = el("button", "btn", cancel); c.onclick = () => done(false); a.appendChild(c); }
      const o = el("button", "btn " + (danger ? "btn-danger" : "btn-primary"), ok); o.onclick = () => done(true); a.appendChild(o);
      d.appendChild(a); ov.appendChild(d); document.body.appendChild(ov); o.focus();
      const onKey = (e) => { if (e.key === "Escape") done(false); };
      document.addEventListener("keydown", onKey);
      ov.addEventListener("mousedown", (e) => { if (e.target === ov && !single) done(false); });
    });
  }

  function avatar(user, cls = "") {
    let node;
    if (user && user.avatar) { node = el("img", "avatar " + cls); node.src = user.avatar; node.alt = ""; node.loading = "lazy"; }
    else { node = el("span", "avatar " + cls); node.style.background = (user && user.color) || "#0f7b6c"; node.textContent = ((user && (user.name || user.username)) || "?").slice(0, 1); }
    if (user && user.online) {
      const w = el("span", "avatar-wrap " + cls); w.appendChild(node); w.appendChild(el("i", "dot")); return w;
    }
    return node;
  }
  const displayName = (u) => (u && (u.name || u.username)) || "";
  function badges(u) {
    const f = document.createDocumentFragment();
    if (u && u.verified) { const b = el("span", "vbadge", "✔"); b.title = "Đã xác minh danh tính"; f.appendChild(b); }
    return f;
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso), now = new Date();
    const hm = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === now.toDateString()) return hm;
    const diff = (now - d) / 86400000;
    if (diff < 6) return d.toLocaleDateString("vi-VN", { weekday: "short" });
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  }
  function fmtAgo(iso) {
    if (!iso) return "";
    const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
    if (s < 60) return "Vừa xong"; if (s < 3600) return `${Math.floor(s / 60)} phút`; if (s < 86400) return `${Math.floor(s / 3600)} giờ`;
    if (s < 604800) return `${Math.floor(s / 86400)} ngày`; return new Date(iso).toLocaleDateString("vi-VN");
  }
  function fmtFull(iso) { return iso ? new Date(iso).toLocaleString("vi-VN") : ""; }
  function fmtSize(n) { return n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
  function lastSeen(iso) {
    if (!iso) return "Ngoại tuyến";
    const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return "Vừa mới hoạt động"; if (m < 60) return `Hoạt động ${m} phút trước`;
    if (m < 1440) return `Hoạt động ${Math.round(m / 60)} giờ trước`; return `Hoạt động ${Math.round(m / 1440)} ngày trước`;
  }

  const SC = window.SC = { api, toast, dialog, avatar, displayName, badges, el, fmtTime, fmtAgo, fmtFull, fmtSize, lastSeen,
    socket: null, me: CFG.me || null, cfg: CFG };

  // ---- menu thả xuống (người dùng, thông báo) ----
  function dropdown(btnId, popId, onOpen) {
    const b = document.getElementById(btnId), p = document.getElementById(popId);
    if (!b || !p) return;
    b.addEventListener("click", (e) => { e.stopPropagation(); const open = p.classList.toggle("hidden") === false; b.setAttribute("aria-expanded", open);
      document.querySelectorAll(".dropdown").forEach((x) => { if (x !== p) x.classList.add("hidden"); }); if (open && onOpen) onOpen(); });
    p.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => { p.classList.add("hidden"); b.setAttribute("aria-expanded", "false"); });
  }
  dropdown("user-menu-btn", "user-menu");

  // ---- giao diện sáng / tối ----
  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) themeBtn.addEventListener("click", async () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { await api("POST", "/api/settings", { dark_mode: dark }, { silent: true }); } catch (e) { /* bỏ qua */ }
  });

  // ---- thông báo ----
  const NOTIF_ICON = { friend_request: "👥", friend_accept: "🤝", comment: "💬", reaction: "👍", share: "↪️", scam_alert: "🚨",
    guardian: "🛡️", guardian_block: "⛔", appeal: "🛡️", call: "📞" };
  function renderNotifs(d) {
    const list = document.getElementById("notif-list"); if (!list) return;
    list.replaceChildren();
    if (!d.notifications.length) { list.appendChild(el("div", "empty", "Chưa có thông báo nào.")); return; }
    d.notifications.forEach((n) => {
      const a = el("a", "notif" + (n.read ? "" : " unread") + (n.level >= 2 ? " danger" : n.level === 1 ? " warn" : ""));
      a.href = n.link || "#";
      a.appendChild(n.actor ? avatar(n.actor, "sm") : el("span", "avatar sm sys", NOTIF_ICON[n.kind] || "🔔"));
      const t = el("div", "ntext"); t.appendChild(el("div", null, (n.actor ? "" : "") + n.text));
      t.appendChild(el("small", null, (NOTIF_ICON[n.kind] || "🔔") + " " + fmtAgo(n.created_at))); a.appendChild(t);
      list.appendChild(a);
    });
  }
  async function loadNotifs() { try { renderNotifs(await api("GET", "/api/notifications", null, { silent: true })); } catch (e) { /* bỏ qua */ } }
  dropdown("notif-btn", "notif-pop", loadNotifs);
  const readAll = document.getElementById("notif-read-all");
  if (readAll) readAll.addEventListener("click", async () => { await api("POST", "/api/notifications/read", null, { silent: true }).catch(() => {}); loadNotifs(); refresh(); });

  const setBadge = (id, n) => { const b = document.getElementById(id); if (b) { b.textContent = n > 99 ? "99+" : n; b.classList.toggle("hidden", !n); } };
  let timer = null;
  const refresh = () => { clearTimeout(timer); timer = setTimeout(async () => {
    try {
      const s = await api("GET", "/api/summary", null, { silent: true });
      setBadge("nav-unread", s.unread_total); setBadge("nav-requests", s.requests); setBadge("nav-notif", s.notifications);
      setBadge("feed-requests", s.requests);
      const m = document.getElementById("model-name"); if (m && s.model) m.textContent = s.model;
      SC.requests = s.requests; document.dispatchEvent(new CustomEvent("sc:summary", { detail: s }));
    } catch (e) { /* bỏ qua */ }
  }, 120); };
  SC.refreshSummary = refresh;

  // ---- socket (chỉ khi đã đăng nhập) ----
  if (SC.me && window.io) {
    SC.socket = io({ transports: ["websocket", "polling"], reconnection: true });
    ["message:new", "conversation:read", "friend:update", "block:update"].forEach((ev) => SC.socket.on(ev, refresh));
    SC.socket.on("connect", refresh);
    SC.socket.on("notify:new", (n) => {
      refresh();
      const pop = document.getElementById("notif-pop"); if (pop && !pop.classList.contains("hidden")) loadNotifs();
      toast(n.text, n.level >= 2 ? "error" : n.level === 1 ? "warn" : "", { icon: NOTIF_ICON[n.kind] || "🔔", href: n.link, ms: n.level >= 2 ? 7000 : 4500 });
    });
    SC.socket.on("system:model_changed", () => { location.href = "/"; });   // quản trị viên đổi mô hình -> đăng xuất
    refresh();
  }
})();
