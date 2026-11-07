/* Trang Tin nhắn: danh sách, bạn bè, chat thời gian thực, cảnh báo 3 lần của Vệ sĩ (AI 3),
   trả lời trích dẫn, thu hồi, thả cảm xúc, ghim tin, tìm trong hội thoại, kho ảnh / tệp / link, tin nhắn thoại. */
(function () {
  "use strict";
  const SC = window.SC, me = SC.me, api = SC.api, socket = SC.socket;
  const $ = (id) => document.getElementById(id);
  const layout = $("chat-layout");
  if (!layout || !me) return;

  const EMOJIS = "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😉 😊 😇 🥰 😍 😘 😋 😛 😜 🤪 🤗 🤔 🤐 😐 😶 🙄 😏 😴 😌 😔 😢 😭 😤 😠 😡 🥺 😱 😨 😰 🤯 😳 🥳 😎 🤓 🤝 👍 👎 👏 🙌 🙏 💪 👌 ✌️ 🤞 👋 ❤️ 🧡 💛 💚 💙 💜 🖤 💔 🔥 ✨ 🎉 🎁 🍀 ☕ 🍜 🍕 🎂 🐶 🐱 ⚠️ 🚫 ✅ ❌ 💯".split(" ");

  const state = {
    convs: new Map(), msgs: new Map(), hasMore: new Map(), activeId: null, tab: "chats",
    friends: [], requests: { incoming: [], outgoing: [] }, blocked: [], search: "", results: [],
    pendingFile: null, sending: false, typingUntil: 0, typingSent: 0, firstConnect: true, loadingOlder: false,
    replyTo: null, mediaKind: "images",
  };
  const REACTIONS = ["❤️", "😂", "😮", "😢", "😡", "👍"];
  const VOICE_MAX = (SC.cfg && SC.cfg.voice_max) || 120;
  const fmtDur = (sec) => { sec = Math.max(0, Math.round(Number(sec) || 0)); return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`; };
  const active = () => state.convs.get(state.activeId) || null;

  /* ---------------------------------------------------------- tiện ích DOM */
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const btn = (label, cls, fn) => { const b = el("button", "btn btn-sm " + (cls || ""), label); b.type = "button"; b.addEventListener("click", (e) => { e.stopPropagation(); fn(b); }); return b; };
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) SC.toast(e.message, "error"); } };

  function linkify(text, parent, clickable) {
    const re = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi; let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      const url = m[0];
      if (clickable) { const a = el("a", null, url); a.href = url.startsWith("www.") ? "https://" + url : url; a.target = "_blank"; a.rel = "noopener noreferrer nofollow"; parent.appendChild(a); }
      else { const s = el("span", null, url); s.style.textDecoration = "underline dotted"; s.title = "Liên kết bị vô hiệu hóa vì tin nhắn nghi lừa đảo"; parent.appendChild(s); }
      last = m.index + url.length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  /* ------------------------------------------------------------ dữ liệu */
  function setConv(c) {
    const old = state.convs.get(c.id);
    state.convs.set(c.id, c);
    return old;
  }
  function sortedConvs(pending) {
    return [...state.convs.values()].filter((c) => (c.last_message_at || c.id === state.activeId) && !!c.request === !!pending)
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || "") || b.id - a.id);
  }
  function updatePendingBadge() {
    const n = sortedConvs(true).filter((c) => c.unread).length, b = $("tab-pending-badge");
    b.textContent = n; b.classList.toggle("hidden", !n);
  }
  function upsertMessage(m) {
    const arr = state.msgs.get(m.conversation_id) || [];
    const i = arr.findIndex((x) => x.id === m.id);
    if (i >= 0) arr[i] = { ...arr[i], ...m }; else { arr.push(m); arr.sort((a, b) => a.id - b.id); }
    state.msgs.set(m.conversation_id, arr);
  }
  const loadConversations = guard(async () => {
    const d = await api("GET", "/api/conversations");
    const fresh = new Map(d.conversations.map((c) => [c.id, c]));
    const a = active();
    if (a && !fresh.has(a.id)) fresh.set(a.id, a);              // giữ cuộc chat trống đang mở
    state.convs = fresh;
    renderList();
    if (state.activeId && state.convs.has(state.activeId)) renderHeader();
  });
  const loadFriends = guard(async () => { state.friends = (await api("GET", "/api/friends")).friends; if (state.tab === "friends" && !state.search) renderList(); });
  const loadRequests = guard(async () => { state.requests = await api("GET", "/api/friend-requests"); });
  const loadBlocked = guard(async () => { state.blocked = (await api("GET", "/api/blocks")).blocked; if (state.tab === "blocked" && !state.search) renderList(); });

  /* ------------------------------------------------------- cột trái: list */
  function convItem(c) {
    const it = el("div", "item" + (c.id === state.activeId ? " active" : "") + (c.unread ? " unread" : ""));
    it.tabIndex = 0; it.setAttribute("role", "button");
    it.appendChild(SC.avatar(c.other, ""));
    const meta = el("div", "meta"), name = el("div", "name"), nm = el("span", null, SC.displayName(c.other));
    if (c.warning > 0 && !c.i_blocked) nm.appendChild(el("span", "warn-mark", c.warning >= 2 ? "🚨" : "⚠️"));
    name.append(nm, el("time", null, SC.fmtTime(c.last_message_at)));
    const lm = c.last_message;
    meta.append(name, el("div", "snippet", lm ? (lm.mine ? "Bạn: " : "") + lm.preview : "Chưa có tin nhắn"));
    it.appendChild(meta);
    if (c.unread) it.appendChild(el("span", "badge", c.unread > 99 ? "99+" : c.unread));
    const open = () => openConversation(c.id);
    it.addEventListener("click", open); it.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    return it;
  }
  function personItem(u, actions) {
    const it = el("div", "item");
    it.appendChild(SC.avatar(u, ""));
    const meta = el("div", "meta"); meta.appendChild(el("div", "name", SC.displayName(u)));
    meta.appendChild(el("div", "snippet", u.online ? "Đang hoạt động" : ""));
    it.appendChild(meta);
    const a = el("div", "actions"); actions.forEach((x) => a.appendChild(x)); it.appendChild(a);
    return it;
  }
  const empty = (icon, text) => { const d = el("div", "empty"); d.append(el("span", "big", icon), document.createTextNode(text)); return d; };

  function renderList() {
    const list = $("list"); list.replaceChildren();
    if (state.search) return renderSearch(list);
    updatePendingBadge();
    if (state.tab === "chats") {
      const cs = sortedConvs(false);
      if (!cs.length) list.appendChild(empty("💬", "Chưa có đoạn chat nào. Vào tab Bạn bè hoặc tìm kiếm để bắt đầu."));
      cs.forEach((c) => list.appendChild(convItem(c)));
    } else if (state.tab === "pending") {
      const cs = sortedConvs(true);
      list.appendChild(el("div", "pending-note", "Tin nhắn từ người chưa là bạn bè. Họ không biết bạn đã đọc cho đến khi bạn trả lời. Vệ sĩ kiểm tra kỹ hơn các tin này."));
      if (!cs.length) list.appendChild(empty("📭", "Không có tin nhắn chờ."));
      cs.forEach((c) => list.appendChild(convItem(c)));
    } else if (state.tab === "friends") {
      if (!state.friends.length) list.appendChild(empty("👥", "Chưa có bạn bè. Gõ tên tài khoản vào ô tìm kiếm để kết bạn."));
      state.friends.forEach((u) => list.appendChild(personItem(u, [
        u.i_blocked ? btn("Bỏ chặn", "", () => unblock(u)) : btn("Nhắn tin", "btn-primary", () => openWithUser(u.id))])));
    } else if (state.tab === "blocked") {
      if (!state.blocked.length) list.appendChild(empty("🛡️", "Bạn chưa chặn ai."));
      state.blocked.forEach((u) => list.appendChild(personItem(u, u.block_source === "guardian"
        ? [btn("🛡️ Khiếu nại", "", () => openAppeal(u)), traceAction(u, u.trace)].filter(Boolean) : [btn("Bỏ chặn", "", () => unblock(u))])));
    }
  }

  function renderSearch(list) {
    list.appendChild(el("div", "section-title", `Kết quả cho “${state.search}”`));
    if (!state.results.length) { list.appendChild(empty("🔎", "Không tìm thấy người dùng nào.")); return; }
    state.results.forEach((u) => {
      let acts = [];
      if (u.i_blocked) acts = [btn("Bỏ chặn", "", () => unblock(u))];
      else if (u.relation === "friend") acts = [btn("Nhắn tin", "btn-primary", () => openWithUser(u.id))];
      else if (u.relation === "sent") acts = [btn("Hủy lời mời", "", () => cancelRequest(u.request_id)), btn("Nhắn tin", "", () => openWithUser(u.id))];
      else if (u.relation === "received") acts = [btn("Chấp nhận", "btn-primary", () => respond(u.request_id, true)), btn("Từ chối", "", () => respond(u.request_id, false))];
      else acts = [btn("Kết bạn", "btn-primary", () => addFriend(u)), btn("Nhắn tin", "", () => openWithUser(u.id))];
      list.appendChild(personItem(u, acts));
    });
  }
  let searchTimer = null, searchSeq = 0;
  $("search").addEventListener("input", (e) => {
    const q = e.target.value.trim(); state.search = q; clearTimeout(searchTimer);
    if (!q) { renderList(); return; }
    searchTimer = setTimeout(guard(async () => {
      const seq = ++searchSeq;
      const d = await api("GET", "/api/users/search?q=" + encodeURIComponent(q));
      if (seq === searchSeq && state.search === q) { state.results = d.users; renderList(); }
    }), 250);
  });
  const refreshSearch = async () => {
    if (!state.search) return;
    try { state.results = (await api("GET", "/api/users/search?q=" + encodeURIComponent(state.search), null, { silent: true })).users; renderList(); } catch (e) { /* bỏ qua */ }
  };
  $("tabs").addEventListener("click", (e) => {
    const t = e.target.closest(".tab"); if (!t) return;
    state.tab = t.dataset.tab; state.search = ""; $("search").value = "";
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    if (state.tab === "friends") loadFriends(); if (state.tab === "blocked") loadBlocked();
    renderList();
  });

  /* ------------------------------------------------- hành động bạn bè/chặn */
  const afterSocial = async () => { await Promise.all([loadFriends(), loadRequests(), loadBlocked(), loadConversations(), refreshSearch()]); };
  const addFriend = guard(async (u) => { await api("POST", "/api/friend-requests", { user_id: u.id }); SC.toast(`Đã gửi lời mời kết bạn tới ${SC.displayName(u)}`, "ok"); await afterSocial(); });
  const respond = guard(async (rid, ok) => { await api("POST", `/api/friend-requests/${rid}/${ok ? "accept" : "decline"}`); SC.toast(ok ? "Đã trở thành bạn bè 🎉" : "Đã từ chối lời mời", ok ? "ok" : ""); await afterSocial(); });
  const cancelRequest = guard(async (rid) => { await api("DELETE", `/api/friend-requests/${rid}`); await afterSocial(); });
  const unblock = guard(async (u) => { await api("DELETE", `/api/blocks/${u.id}`); SC.toast(`Đã bỏ chặn ${SC.displayName(u)}`, "ok"); await afterSocial(); });
  const unfriend = guard(async (u) => {
    if (!(await SC.dialog({ title: `Hủy kết bạn với ${SC.displayName(u)}?`, text: "Hai bạn sẽ không thể nhắn tin cho nhau cho đến khi kết bạn lại.", ok: "Hủy kết bạn", danger: true }))) return;
    await api("DELETE", `/api/friends/${u.id}`); await afterSocial();
  });
  const blockUser = guard(async (u) => {
    const okk = await SC.dialog({ title: `Chặn ${SC.displayName(u)}?`, icon: "🛡️", danger: true, ok: "Chặn",
      text: `${SC.displayName(u)} sẽ không thể nhắn tin cho bạn và bạn cũng không nhắn được cho họ. Lịch sử trò chuyện vẫn được giữ. Bạn có thể bỏ chặn bất cứ lúc nào.` });
    if (!okk) return;
    await api("POST", "/api/blocks", { user_id: u.id }); SC.toast(`Đã chặn ${SC.displayName(u)}`, "ok"); await afterSocial();
  });

  /* ------------------------------------------------------- mở cuộc trò chuyện */
  const openWithUser = guard(async (uid) => {
    const d = await api("POST", "/api/conversations", { user_id: uid });
    setConv(d.conversation); await openConversation(d.conversation.id);
    state.tab = "chats"; state.search = ""; $("search").value = "";
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === "chats"));
    renderList();
  });

  const openConversation = guard(async (cid) => {
    state.activeId = cid;
    $("chat-empty").classList.add("hidden"); $("chat-box").classList.remove("hidden"); layout.classList.add("show-chat");
    clearAttachment(); clearReply(); stopRec(true); closeSearch(); closeMedia(); $("input").value = ""; autosize(); $("typing").textContent = "";
    let detail;
    try { detail = (await api("GET", `/api/conversations/${cid}`)).conversation; }
    catch (e) { state.activeId = null; $("chat-box").classList.add("hidden"); $("chat-empty").classList.remove("hidden"); layout.classList.remove("show-chat"); history.replaceState(null, "", "/messages"); throw e; }
    setConv(detail);
    const h = await api("GET", `/api/conversations/${cid}/messages`);
    state.msgs.set(cid, h.messages); state.hasMore.set(cid, h.has_more);
    history.replaceState(null, "", `/messages/${cid}`);
    renderList(); renderHeader(); renderPinned(); renderBanners(); renderMessages(true); renderComposerState();
    markRead(); if (!matchMedia("(max-width:860px)").matches) $("input").focus();
  });

  const markRead = async () => {
    const c = active(); if (!c || document.hidden) return;
    if (!c.unread && !(state.msgs.get(c.id) || []).some((m) => !m.mine && !m.read_at)) return;
    try {
      await api("POST", `/api/conversations/${c.id}/read`, null, { silent: true });
      c.unread = 0; (state.msgs.get(c.id) || []).forEach((m) => { if (!m.mine && !m.read_at) m.read_at = new Date().toISOString(); });
      renderList(); SC.refreshSummary && SC.refreshSummary();
    } catch (e) { /* bỏ qua */ }
  };

  /* --------------------------------------------------------- tiêu đề khung chat */
  function statusText(c) {
    if (c.i_blocked || c.blocked_me) return "";
    if (c.other.online) return "Đang hoạt động";
    return SC.lastSeen(c.other.last_seen);
  }
  function renderHeader() {
    const c = active(); if (!c) return;
    $("head-avatar").replaceChildren(SC.avatar(c.other, ""));
    $("head-name").textContent = SC.displayName(c.other);
    $("head-status").textContent = statusText(c);
    const menu = $("head-menu"); menu.replaceChildren();
    const mk = (label, fn, danger) => { const b = el("button", null, label); b.type = "button"; if (danger) b.style.color = "var(--red)"; b.addEventListener("click", () => { menu.classList.add("hidden"); fn(); }); return b; };
    menu.appendChild(mk("👤 Xem trang cá nhân", () => { location.href = `/u/${encodeURIComponent(c.other.username)}`; }));
    menu.appendChild(mk("🔍 Tìm trong cuộc trò chuyện", () => $("msearch-btn").click()));
    menu.appendChild(mk("🗂️ Ảnh, tệp và link", () => $("media-btn").click()));
    if (c.guardian_block) menu.appendChild(mk("🛡️ Khiếu nại gỡ chặn", () => { const ap = c.guardian_block.appeal || {}; if (ap.status === "open") location.href = `/appeal/${ap.id}`; else openAppeal(c.other); }));
    else if (c.i_blocked) menu.appendChild(mk("✅ Bỏ chặn " + SC.displayName(c.other), () => unblock(c.other)));
    else menu.appendChild(mk("🚫 Chặn " + SC.displayName(c.other), () => blockUser(c.other), true));
    if (c.is_friend) menu.appendChild(mk("💔 Hủy kết bạn", () => unfriend(c.other), true));
    const canCall = c.can_send && !!SC.startCall;
    $("call-audio-btn").disabled = $("call-video-btn").disabled = !canCall;
  }
  $("ask-btn").addEventListener("click", () => { const c = active(); if (c && SC.guard) SC.guard.askDialog(c.id, SC.displayName(c.other)); });
  $("ask-paste-btn").addEventListener("click", () => { if (SC.guard) SC.guard.askDialog(null); });
  $("call-audio-btn").addEventListener("click", () => { const c = active(); if (c && SC.startCall) SC.startCall(c.id, false); });
  $("call-video-btn").addEventListener("click", () => { const c = active(); if (c && SC.startCall) SC.startCall(c.id, true); });
  $("head-menu-btn").addEventListener("click", (e) => { e.stopPropagation(); $("head-menu").classList.toggle("hidden"); });
  document.addEventListener("click", () => { $("head-menu").classList.add("hidden"); $("emoji-pop").classList.add("hidden"); });
  $("back-btn").addEventListener("click", () => { layout.classList.remove("show-chat"); history.replaceState(null, "", "/messages"); });

  /* ---------------------------------------------------- banner cảnh báo 3 mức */
  const BANNERS = {
    1: { icon: "⚠️", title: "Cảnh báo lần 1", text: (n) => `${n} đã gửi 1 tin có dấu hiệu lừa đảo. Đừng chuyển tiền, đừng cung cấp mã OTP hay mật khẩu.` },
    2: { icon: "🚨", title: "Cảnh báo lần 2 — tin đã bị che", text: (n) => `${n} gửi tin lừa đảo lần thứ 2. Nếu thêm 1 lần nữa, Vệ sĩ sẽ tự động chặn người này.` },
    3: { icon: "⛔", title: "Lần 3 — Vệ sĩ đã tự động chặn", text: (n) => `${n} gửi tin lừa đảo 3 lần nên đã bị chặn. Nếu là người thân bị chặn nhầm, hãy gửi Khiếu nại.` },
  };
  function renderBanners(pulse) {
    const box = $("banner-box"), c = active(); box.replaceChildren(); if (!c) return;
    if (!c.is_friend && !c.i_blocked) {
      // Banner người lạ do guard_ui.js dựng; dự phòng nếu chưa nạp
      const slot = el("div", "stranger-slot"); box.appendChild(slot);
      if (SC.guard && SC.guard.strangerBanner) SC.guard.strangerBanner(slot, c);
      else { const b = el("div", "banner l1"); const t = el("div", "btxt"); t.append(el("b", null, "Người này chưa là bạn bè của bạn"), document.createTextNode(`${c.mutual || 0} bạn chung. Hãy thận trọng với yêu cầu chuyển tiền hoặc cung cấp thông tin.`)); b.append(el("div", "bicon", "👤"), t); slot.appendChild(b); }
    }
    if (c.warning > 0 && !c.i_blocked) {
      const cfg = BANNERS[c.warning];
      const b = el("div", `banner l${c.warning}` + (pulse && c.warning >= 3 ? " pulse" : "")); b.setAttribute("role", "alert");
      const t = el("div", "btxt"); t.append(el("b", null, cfg.title), document.createTextNode(cfg.text(SC.displayName(c.other))));
      b.append(el("div", "bicon", cfg.icon), t);

      box.appendChild(b);
    }
    if (c.self_warning) {
      const b = el("div", "banner l3 self" + (pulse ? " pulse" : "")); b.setAttribute("role", "alert");
      const t = el("div", "btxt"); t.append(el("b", null, "CẢNH BÁO TỪ HỆ THỐNG"), document.createTextNode(SELF_TEXT));
      b.append(el("div", "bicon", "🚨"), t); box.appendChild(b);
    }
  }
  const SELF_TEXT = "Hệ thống phát hiện bạn đang là đối tượng đi lừa đảo người khác, hãy dừng lại không thì bạn sẽ đi TÒ";

  /* --------------------------------------------------------- hiển thị tin nhắn */
  const dayKey = (iso) => new Date(iso).toDateString();
  const dayLabel = (iso) => { const d = new Date(iso), n = new Date(); if (d.toDateString() === n.toDateString()) return "Hôm nay"; const y = new Date(n - 864e5); if (d.toDateString() === y.toDateString()) return "Hôm qua"; return d.toLocaleDateString("vi-VN"); };

  // Thân tin: link nghi vấn bị làm mờ, STK có nút copy (đếm ngược ở mức 2+) - do guard_ui.js dựng
  function linkifyGuard(text, parent, m) {
    if (SC.guard && SC.guard.renderBody && !m.mine) SC.guard.renderBody(text, m, parent);
    else linkify(text, parent, true);
  }
  const revealed = new Set();
  function maskedBubble(m) {
    const b = el("div", "bubble masked flag-3");
    const g = m.guard || {}, voice = m.kind === "voice";
    if (g.unreadable) b.append(el("b", null, voice ? "🛡️ Tin nhắn thoại bị che" : "🛡️ Tin nhắn bị che"),
      el("span", "mk-sub", "Người gửi đã bị cảnh báo lừa đảo từ lần 2 trong cuộc trò chuyện này. Vệ sĩ không đọc được nội dung tin này."));
    else b.append(el("b", null, "🛡️ Vệ sĩ đã che tin nhắn nguy hiểm"), el("span", "mk-sub", "Tin này có dấu hiệu lừa đảo rõ ràng. Đừng làm theo yêu cầu trong tin."));
    const show = el("button", "btn btn-sm", voice ? "Vẫn nghe" : "Vẫn xem nội dung"); show.type = "button";
    show.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (await SC.dialog({ title: "Xem tin nhắn nguy hiểm?", icon: "⛔", danger: true, ok: "Tôi hiểu, vẫn xem", text: "Chỉ đọc để biết, KHÔNG chuyển tiền, KHÔNG bấm link, KHÔNG cài ứng dụng trong tin này." })) { revealed.add(m.id); renderMessages(false); }
    });
    b.appendChild(show); return b;
  }
  let playing = null;
  function voiceBubble(m) {
    const a = m.attachment, b = el("div", "bubble voice");
    const audio = new Audio(); audio.preload = "none"; audio.src = a.url;
    const play = el("button", "vplay", "▶"); play.type = "button"; play.setAttribute("aria-label", "Phát tin nhắn thoại");
    const bar = el("div", "vbar"), fill = el("i"), time = el("small", "vtime", fmtDur(a.duration));
    bar.appendChild(fill);
    const total = () => (isFinite(audio.duration) && audio.duration > 0 ? audio.duration : (a.duration || 1));
    play.addEventListener("click", (e) => {
      e.stopPropagation();
      if (audio.paused) { if (playing && playing !== audio) playing.pause(); playing = audio; audio.play().catch(() => SC.toast("Không phát được tin nhắn thoại.", "error")); }
      else audio.pause();
    });
    bar.addEventListener("click", (e) => { e.stopPropagation(); const r = bar.getBoundingClientRect(); audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * total(); });
    audio.addEventListener("play", () => { play.textContent = "⏸"; });
    audio.addEventListener("pause", () => { play.textContent = "▶"; });
    audio.addEventListener("ended", () => { play.textContent = "▶"; fill.style.width = "0%"; time.textContent = fmtDur(a.duration); });
    audio.addEventListener("timeupdate", () => { fill.style.width = Math.min(100, audio.currentTime / total() * 100) + "%"; time.textContent = fmtDur(audio.currentTime); });
    b.append(play, bar, time);
    return b;
  }
  function bubbleFor(m) {
    if (m.recalled) return el("div", "bubble recalled", m.mine ? "Bạn đã thu hồi tin nhắn" : "Tin nhắn đã bị thu hồi");
    if (!m.mine && m.guard && m.guard.mask && !revealed.has(m.id)) return maskedBubble(m);
    if (m.kind === "voice" && m.attachment) return voiceBubble(m);
    if (m.kind === "image" && m.attachment) {
      const b = el("div", "bubble img"); const img = el("img"); img.src = m.attachment.url; img.alt = m.attachment.name || "Ảnh"; img.loading = "lazy";
      img.addEventListener("click", () => lightbox(m.attachment.url));
      img.addEventListener("load", () => { if (nearBottom._stick) scrollBottom(); });
      b.appendChild(img);
      if (m.body) { const cap = el("span", "cap"); linkifyGuard(m.body, cap, m); b.appendChild(cap); b.style.background = m.mine ? "var(--bubble-me)" : "var(--bubble-other)"; b.style.color = m.mine ? "#fff" : ""; b.classList.remove("img"); b.style.padding = "3px"; }
      return b;
    }
    if (m.kind === "file" && m.attachment) {
      const wrap = el("div");
      const info = el("div"); info.append(el("b", null, m.attachment.name), el("small", null, SC.fmtSize(m.attachment.size || 0) + (m.attachment.is_apk ? " · Tệp cài đặt Android" : "")));
      if (m.attachment.blocked) {
        const a = el("div", "fileCard blocked"); a.append(el("span", "ficon", "⛔"), info);
        info.appendChild(el("small", "blocked-why", "Vệ sĩ đã chặn tải xuống. Cơ quan nhà nước, ngân hàng không bao giờ gửi ứng dụng qua tin nhắn."));
        wrap.appendChild(a);
      } else {
        const a = el("a", "fileCard"); a.href = m.attachment.url; a.setAttribute("download", m.attachment.name || "tep");
        a.append(el("span", "ficon", m.attachment.is_apk ? "📦" : "📄"), info); wrap.appendChild(a);
        if (m.attachment.is_apk && !m.mine) a.addEventListener("click", async (e) => {
          e.preventDefault();
          const ok = await SC.dialog({ title: "Tải tệp cài đặt (.apk)?", icon: "📦", danger: true, ok: "Vẫn tải xuống",
            text: "Tệp .apk có thể chứa phần mềm độc hại chiếm quyền điện thoại, đọc tin nhắn OTP. Chỉ cài ứng dụng từ CH Play / App Store." });
          if (ok) location.href = m.attachment.url;
        });
      }
      if (m.body) { const b = el("div", "bubble" + (m.warning_level ? " flag-" + m.warning_level : "")); linkifyGuard(m.body, b, m); b.style.marginTop = "3px"; wrap.appendChild(b); }
      return wrap;
    }
    const b = el("div", "bubble" + (m.warning_level && !m.mine ? " flag-" + m.warning_level : "")); linkifyGuard(m.body || "", b, m); return b;
  }
  function callLog(m) {
    const row = el("div", "call-log"); row.dataset.id = m.id;
    row.append(el("span", null, m.body || "📞 Cuộc gọi"), el("small", null, new Date(m.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })));
    return row;
  }
  function guardNodes(m, c) {
    if (m.mine || m.kind === "call") return null;
    if (m.recalled) return m.warning_level ? el("div", "flaglabel l" + Math.min(m.warning_level, 3), `🛡️ Tin này đã bị Vệ sĩ cảnh báo (lần ${m.warning_level}) trước khi bị thu hồi`) : null;
    if (m.kind === "voice" && !c.is_friend && !(m.guard && m.guard.mask)) return el("div", "voice-note", "⚠️ Vệ sĩ không kiểm tra được tin nhắn thoại. Cẩn thận giọng nói giả làm người quen.");
    if (m.scan === "pending") return el("div", "scan-pending", "🛡️ Vệ sĩ đang kiểm tra…");
    if (SC.guard && SC.guard.explainCard && m.guard)
      return SC.guard.explainCard(m, c, { rerender: () => renderMessages(false), block: () => blockUser(c.other) });
    return flagLabel(m, c);
  }
  function flagLabel(m, c) {
    const L = m.warning_level; if (!L || m.mine) return null;
    const txt = { 1: "⚠️ Lần 1 · Tin nhắn có dấu hiệu lừa đảo", 2: "🚨 Lần 2 · Nghi ngờ lừa đảo cao", 3: "Lần 3+ · Nguy cơ lừa đảo rất cao" }[L];
    const d = el("div", "flaglabel l" + Math.min(L, 3));
    if (L >= 3) d.appendChild(el("span", "shake", "🚨"));
    d.appendChild(el("span", null, txt));
    return d;
  }
  function statusLine(m) {
    const s = el("div", "status");
    s.textContent = m.read_at ? "Đã xem" : m.delivered_at ? "Đã nhận" : "Đã gửi"; s.title = SC.fmtFull(m.read_at || m.delivered_at || m.created_at);
    return s;
  }
  function nearBottom() { const m = $("msgs"); const v = m.scrollHeight - m.scrollTop - m.clientHeight < 140; nearBottom._stick = v; return v; }
  const scrollBottom = () => { const m = $("msgs"); m.scrollTop = m.scrollHeight; };

  function renderMessages(forceBottom) {
    const c = active(), box = $("msgs"); if (!c) return;
    const stick = forceBottom || nearBottom();
    const arr = state.msgs.get(c.id) || [];
    const frag = document.createDocumentFragment();
    if (state.hasMore.get(c.id)) frag.appendChild(el("div", "day-sep", "Cuộn lên để xem tin cũ hơn…"));
    if (!arr.length) { const d = el("div", "empty"); d.append(el("span", "big", "👋"), document.createTextNode(`Hãy gửi lời chào tới ${SC.displayName(c.other)}!`)); frag.appendChild(d); }
    const lastMine = [...arr].reverse().find((x) => x.mine);
    arr.forEach((m, i) => {
      const prev = arr[i - 1], next = arr[i + 1];
      if (!prev || dayKey(prev.created_at) !== dayKey(m.created_at)) frag.appendChild(el("div", "day-sep", dayLabel(m.created_at)));
      if (m.kind === "call") { frag.appendChild(callLog(m)); return; }
      const sameP = prev && prev.kind !== "call" && prev.sender_id === m.sender_id && dayKey(prev.created_at) === dayKey(m.created_at) && (new Date(m.created_at) - new Date(prev.created_at)) < 300000;
      const sameN = next && next.sender_id === m.sender_id && dayKey(next.created_at) === dayKey(m.created_at) && (new Date(next.created_at) - new Date(m.created_at)) < 300000;
      const row = el("div", "mrow" + (m.mine ? " mine" : "") + (sameP ? "" : " gap")); row.dataset.id = m.id;
      if (!m.mine) { if (!sameN) row.appendChild(SC.avatar(c.other, "sm")); else { const sp = el("span"); sp.style.width = "32px"; sp.style.flex = "none"; row.appendChild(sp); } }
      const stack = el("div", "stack"); stack.title = SC.fmtFull(m.created_at);
      if (m.reply_to && !m.recalled) stack.appendChild(quoteNode(m, c));
      stack.appendChild(bubbleFor(m));
      const rc = reactionChips(m, c); if (rc) stack.appendChild(rc);
      const fl = guardNodes(m, c); if (fl) stack.appendChild(fl);
      if (!sameN || m.pinned) stack.appendChild(el("div", "tmeta", (m.pinned ? "📌 Đã ghim · " : "") + new Date(m.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })));
      if (m.mine && lastMine && m.id === lastMine.id) stack.appendChild(statusLine(m));
      stack.addEventListener("click", () => { document.querySelectorAll(".mrow.show-actions").forEach((r) => { if (r !== row) r.classList.remove("show-actions"); }); row.classList.toggle("show-actions"); });
      const acts = m.recalled ? null : msgActions(m, c);
      if (m.mine && acts) row.append(acts, stack); else { row.appendChild(stack); if (acts) row.appendChild(acts); }
      frag.appendChild(row);
    });
    const prevH = box.scrollHeight, prevT = box.scrollTop;
    box.replaceChildren(frag);
    if (stick) scrollBottom(); else if (renderMessages._keep) box.scrollTop = prevT + (box.scrollHeight - prevH);
  }

  /* --------------------------------------------- trích dẫn / cảm xúc / thao tác trên tin */
  function previewOf(m) {
    if (m.recalled) return "Tin nhắn đã bị thu hồi";
    if (!m.mine && m.guard && m.guard.mask && !revealed.has(m.id)) return "🛡️ Tin nhắn đã bị che";
    if (m.kind === "voice") return `🎤 Tin nhắn thoại (${fmtDur(m.attachment && m.attachment.duration)})`;
    if (m.kind === "image") return "📷 Ảnh" + (m.body ? ": " + m.body : "");
    if (m.kind === "file") return "📎 " + ((m.attachment && m.attachment.name) || "Tệp");
    return m.body || "";
  }
  function quoteNode(m, c) {
    const q = m.reply_to, d = el("button", "quote"); d.type = "button";
    const who = q.mine ? (m.mine ? "chính mình" : "bạn") : SC.displayName(c.other);
    d.append(el("small", null, `↩ ${m.mine ? "Bạn" : SC.displayName(c.other)} trả lời ${who}`), el("span", null, q.preview || ""));
    d.addEventListener("click", (e) => { e.stopPropagation(); if (q.id) jumpTo(q.id); });
    return d;
  }
  function reactionChips(m, c) {
    const r = m.reactions; if (!r || !Object.keys(r.counts || {}).length) return null;
    const w = el("div", "reacts");
    Object.entries(r.counts).forEach(([e, n]) => {
      const b = el("button", "react-chip" + (r.mine === e ? " mine" : ""), `${e} ${n}`); b.type = "button";
      b.title = r.mine === e ? "Bấm để gỡ cảm xúc của bạn" : "Thả cảm xúc này"; b.disabled = !c.can_send;
      b.addEventListener("click", (ev) => { ev.stopPropagation(); react(m, e); });
      w.appendChild(b);
    });
    return w;
  }
  function closePops() { document.querySelectorAll(".msg-pop").forEach((x) => x.remove()); }
  function msgActions(m, c) {
    const bar = el("div", "msg-actions");
    const mk = (ico, title, fn) => { const b = el("button", "ma-btn", ico); b.type = "button"; b.title = title; b.setAttribute("aria-label", title); b.addEventListener("click", (e) => { e.stopPropagation(); fn(b); }); return b; };
    if (c.can_send && m.kind !== "call") {
      bar.appendChild(mk("😊", "Thả cảm xúc", (b) => {
        closePops(); const pop = el("div", "msg-pop react-pop");
        REACTIONS.forEach((e) => { const x = el("button", m.reactions && m.reactions.mine === e ? "on" : "", e); x.type = "button"; x.addEventListener("click", (ev) => { ev.stopPropagation(); closePops(); react(m, e); }); pop.appendChild(x); });
        b.parentElement.appendChild(pop);
      }));
      bar.appendChild(mk("↩️", "Trả lời", () => startReply(m, c)));
    }
    bar.appendChild(mk("⋯", "Thêm", (b) => {
      closePops(); const pop = el("div", "msg-pop more-pop");
      const item = (label, fn, danger) => { const x = el("button", danger ? "danger" : "", label); x.type = "button"; x.addEventListener("click", (ev) => { ev.stopPropagation(); closePops(); fn(); }); pop.appendChild(x); };
      item(m.pinned ? "📌 Bỏ ghim" : "📌 Ghim tin nhắn", () => pinMsg(m.id, !m.pinned));
      if (m.body && (m.mine || !m.warning_level)) item("📋 Sao chép chữ", async () => { try { await navigator.clipboard.writeText(m.body); SC.toast("Đã sao chép", "ok"); } catch (e) { SC.toast("Không sao chép được.", "error"); } });
      if (m.can_recall) item("↶ Thu hồi với mọi người", () => recallMsg(m), true);
      b.parentElement.appendChild(pop);
    }));
    return bar;
  }
  document.addEventListener("click", closePops);
  const react = guard(async (m, emoji) => { const d = await api("POST", `/api/messages/${m.id}/react`, { emoji }); upsertMessage(d.message); renderMessages(false); });
  const pinMsg = guard(async (id, on) => { await api("POST", `/api/messages/${id}/pin`, { pinned: on }); SC.toast(on ? "Đã ghim tin nhắn" : "Đã bỏ ghim", "ok"); await refreshActive(); });
  const recallMsg = guard(async (m) => {
    if (!(await SC.dialog({ title: "Thu hồi tin nhắn?", icon: "↶", ok: "Thu hồi", danger: true,
      text: "Tin nhắn sẽ bị ẩn với cả hai bên. Lưu ý: nếu tin đã bị Vệ sĩ cảnh báo lừa đảo, lần cảnh báo vẫn được giữ." }))) return;
    const d = await api("POST", `/api/messages/${m.id}/recall`); upsertMessage(d.message); renderMessages(false);
  });

  /* ------------------------------------------------------------- trả lời */
  function startReply(m, c) {
    state.replyTo = { id: m.id, who: m.mine ? "chính bạn" : SC.displayName(c.other), preview: previewOf(m) };
    renderReply(); input.focus();
  }
  function clearReply() { state.replyTo = null; renderReply(); }
  function renderReply() {
    const slot = $("reply-slot"); slot.replaceChildren(); const r = state.replyTo; if (!r) return;
    const bar = el("div", "reply-bar"); const t = el("div", "rb-text");
    t.append(el("b", null, `↩ Đang trả lời ${r.who}`), el("span", null, r.preview.slice(0, 140)));
    bar.append(t, btn("✕", "", clearReply)); slot.appendChild(bar);
  }

  /* --------------------------------------------------- nhảy tới 1 tin (tìm kiếm / ghim / trích dẫn) */
  const jumpTo = guard(async (id) => {
    const c = active(); if (!c) return;
    if (!(state.msgs.get(c.id) || []).some((m) => m.id === id)) {
      const h = await api("GET", `/api/conversations/${c.id}/messages?around=${id}`);
      state.msgs.set(c.id, h.messages); state.hasMore.set(c.id, h.has_more); renderMessages(false);
    }
    const row = $("msgs").querySelector(`.mrow[data-id="${id}"]`);
    if (!row) { SC.toast("Tin nhắn không còn hiển thị.", ""); return; }
    row.scrollIntoView({ block: "center", behavior: "smooth" });
    row.classList.add("flash-msg"); setTimeout(() => row.classList.remove("flash-msg"), 2200);
  });

  /* ------------------------------------------------------------- tin ghim */
  let pinsOpen = false;
  function renderPinned() {
    const c = active(), bar = $("pinned-bar"), list = (c && c.pinned) || [];
    bar.classList.toggle("hidden", !list.length); bar.replaceChildren(); if (!list.length) { pinsOpen = false; return; }
    const row = (p, first) => {
      const r = el("div", "pin-row");
      const main = el("button", "pin-main"); main.type = "button"; main.title = "Đi tới tin nhắn";
      main.append(el("span", "pin-ico", "📌"), el("span", "pin-txt", (p.mine ? "Bạn: " : "") + p.preview));
      main.addEventListener("click", () => jumpTo(p.id)); r.appendChild(main);
      if (first && list.length > 1) { const t = btn(pinsOpen ? "Thu gọn" : `${list.length} tin ghim`, "", () => { pinsOpen = !pinsOpen; renderPinned(); }); r.appendChild(t); }
      const un = el("button", "icon-btn sm", "✕"); un.type = "button"; un.title = "Bỏ ghim"; un.setAttribute("aria-label", "Bỏ ghim");
      un.addEventListener("click", () => pinMsg(p.id, false)); r.appendChild(un);
      return r;
    };
    (pinsOpen ? list : list.slice(0, 1)).forEach((p, i) => bar.appendChild(row(p, i === 0)));
  }

  /* --------------------------------------------------- tìm trong cuộc trò chuyện */
  function closeSearch() { $("msearch").classList.add("hidden"); $("msearch-results").classList.add("hidden"); $("msearch-input").value = ""; }
  $("msearch-btn").addEventListener("click", () => { const s = $("msearch"); s.classList.toggle("hidden"); if (!s.classList.contains("hidden")) $("msearch-input").focus(); else closeSearch(); });
  $("msearch-close").addEventListener("click", closeSearch);
  let msTimer = null;
  $("msearch-input").addEventListener("input", (e) => {
    clearTimeout(msTimer); const q = e.target.value.trim(), box = $("msearch-results");
    if (q.length < 2) { box.classList.add("hidden"); return; }
    msTimer = setTimeout(guard(async () => {
      const c = active(); if (!c) return;
      const d = await api("GET", `/api/conversations/${c.id}/search?q=${encodeURIComponent(q)}`);
      box.replaceChildren(); box.classList.remove("hidden");
      if (!d.results.length) { box.appendChild(el("div", "empty small", `Không có tin nhắn nào chứa “${q}”.`)); return; }
      d.results.forEach((r) => {
        const it = el("button", "ms-item"); it.type = "button";
        it.append(el("b", null, r.mine ? "Bạn" : SC.displayName(c.other)), el("span", null, r.preview), el("small", null, SC.fmtFull(r.created_at)));
        it.addEventListener("click", () => { box.classList.add("hidden"); jumpTo(r.id); });
        box.appendChild(it);
      });
    }), 300);
  });
  $("msearch-input").addEventListener("keydown", (e) => { if (e.key === "Escape") closeSearch(); });

  /* ------------------------------------------------- kho ảnh / tệp / link */
  function closeMedia() { $("media-drawer").classList.add("hidden"); }
  $("media-btn").addEventListener("click", () => { const d = $("media-drawer"); d.classList.toggle("hidden"); if (!d.classList.contains("hidden")) loadMedia(); });
  $("media-close").addEventListener("click", closeMedia);
  $("media-tabs").addEventListener("click", (e) => {
    const t = e.target.closest(".tab"); if (!t) return;
    state.mediaKind = t.dataset.kind; document.querySelectorAll("#media-tabs .tab").forEach((x) => x.classList.toggle("active", x === t)); loadMedia();
  });
  const loadMedia = guard(async () => {
    const c = active(), body = $("media-body"); if (!c) return;
    const kind = state.mediaKind, d = await api("GET", `/api/conversations/${c.id}/media?kind=${kind}`);
    body.replaceChildren();
    if (!d.items.length) { body.appendChild(empty(kind === "images" ? "🖼️" : kind === "files" ? "📁" : "🔗", "Chưa có gì ở đây.")); return; }
    if (kind === "images") {
      const g = el("div", "md-grid");
      d.items.forEach((it) => {
        const cell = el("button", "md-img"); cell.type = "button";
        if (it.hidden) { cell.classList.add("hidden-img"); cell.appendChild(el("span", null, "🛡️ Ảnh bị che")); }
        else { const i = el("img"); i.src = it.url; i.alt = "Ảnh"; i.loading = "lazy"; cell.appendChild(i); }
        cell.title = "Đi tới tin nhắn"; cell.addEventListener("click", () => { closeMedia(); jumpTo(it.id); }); g.appendChild(cell);
      });
      body.appendChild(g);
    } else d.items.forEach((it) => {
      const r = el("div", "md-row" + (it.danger || it.blocked ? " danger" : ""));
      if (kind === "files") r.append(el("span", "md-ico", it.kind === "voice" ? "🎤" : it.is_apk ? "📦" : "📄"), el("span", "md-name", it.name), el("small", null, it.blocked ? "⛔ Bị chặn tải" : (it.size ? SC.fmtSize(it.size) : "")));
      else r.append(el("span", "md-ico", it.danger ? "⚠️" : "🔗"), el("span", "md-name", it.url), el("small", null, it.danger ? "Trong tin bị cảnh báo" : SC.fmtTime(it.created_at)));
      const go = btn("Xem", "", () => { closeMedia(); jumpTo(it.id); }); r.appendChild(go);
      body.appendChild(r);
    });
  });

  function renderComposerState() {
    const c = active(); if (!c) return;
    const blocked = !c.can_send;
    $("composer-inner").classList.toggle("hidden", blocked);
    const bar = $("blocked-bar"); bar.classList.toggle("hidden", !blocked); bar.replaceChildren();
    if (blocked && c.guardian_block) {
      bar.classList.add("guardian"); bar.appendChild(guardianBlockBox(c));
    } else if (blocked) {
      bar.classList.remove("guardian");
      bar.appendChild(document.createTextNode(c.send_block_reason || "Không thể nhắn tin."));
      if (c.i_blocked) { bar.appendChild(document.createTextNode(" ")); bar.appendChild(btn("Bỏ chặn", "btn-primary", () => unblock(c.other))); }
    }
    updateSend();
  }

  // Vệ sĩ đã TỰ ĐỘNG chặn (lần 3): chỉ gỡ qua Khiếu nại (2 bên chụp ảnh trực tiếp + xác nhận nhau)
  function guardianBlockBox(c) {
    const gb = c.guardian_block, ap = gb.appeal || {};
    const box = el("div", "gblock");
    box.appendChild(el("div", "gb-ico", "⛔"));
    const t = el("div", "gb-text");
    t.appendChild(el("b", null, gb.role === "protected" ? `Vệ sĩ đã tự động chặn ${SC.displayName(c.other)}` : "Bạn đã bị hệ thống chặn nhắn tin"));
    t.appendChild(el("div", null, c.send_block_reason || ""));
    if (ap.status === "open") t.appendChild(el("div", "gb-st", "🕓 Đang có khiếu nại chờ xác minh."));
    else if (ap.status === "failed" || ap.status === "expired") t.appendChild(el("div", "gb-st bad", `Khiếu nại trước: ${ap.fail_reason || "không thành công"}`));
    box.appendChild(t);
    if (ap.status === "open") box.appendChild(btn("Tiếp tục khiếu nại", "btn-primary", () => { location.href = `/appeal/${ap.id}`; }));
    else if (ap.can_open) box.appendChild(btn(`🛡️ Khiếu nại gỡ chặn (còn ${ap.remaining} lần)`, "btn-primary", () => openAppeal(c.other)));
    else box.appendChild(el("span", "muted small", "Đã hết lượt khiếu nại."));
    const tr = traceAction(c.other, gb.trace);
    if (tr) box.appendChild(tr);
    return box;
  }

  // Nạn nhân xin xem thông tin truy vết (IP, vị trí gần đúng) của kẻ gian -> quản trị viên duyệt
  function traceAction(u, trace) {
    if (!trace) return null;
    if (trace.status === "pending") return el("span", "muted small", "🕓 Đã gửi yêu cầu truy vết");
    if (trace.status === "approved") { const a = el("a", "btn", "🔎 Xem thông tin truy vết"); a.href = "/trace-requests"; return a; }
    return btn(trace.status === "rejected" ? "🔎 Gửi lại yêu cầu truy vết" : "🔎 Yêu cầu thông tin truy vết", "", () => requestTrace(u));
  }
  const requestTrace = guard(async (u) => {
    const body = el("div", "trace-form");
    const ta = el("textarea", "input"); ta.rows = 4; ta.maxLength = 500;
    ta.placeholder = "Lý do (ví dụ: tôi đã bị lừa chuyển tiền và cần nộp thông tin cho công an)";
    body.appendChild(ta);
    const ok = await SC.dialog({ title: "Yêu cầu thông tin truy vết", icon: "🔎", ok: "Gửi yêu cầu", body,
      text: `Vệ sĩ đã lưu IP và vị trí gần đúng của ${SC.displayName(u)} khi tự động chặn. Chỉ quản trị viên xem được. ` +
        "Gửi yêu cầu kèm lý do, quản trị viên duyệt xong bạn sẽ nhận thông báo và xem được thông tin này." });
    if (!ok) return;
    await api("POST", "/api/trace-requests", { user_id: u.id, reason: ta.value });
    SC.toast("Đã gửi yêu cầu truy vết tới quản trị viên", "ok");
    await afterSocial();
  });
  const openAppeal = guard(async (u) => {
    const ok = await SC.dialog({ title: "Khiếu nại gỡ chặn", icon: "🛡️", ok: "Bắt đầu khiếu nại",
      text: `Hai bên (bạn và ${SC.displayName(u)}) sẽ chụp ảnh trực tiếp bằng camera và xác nhận nhau là người thân / người quen. ` +
        "Nếu đã đặt Mật mã gia đình, người bị chặn phải trả lời đúng. Có 24 giờ để hoàn tất. Gỡ chặn xong, Vệ sĩ đếm lại từ lần 1." });
    if (!ok) return;
    const d = await api("POST", "/api/appeals", { user_id: u.id });
    location.href = `/appeal/${d.appeal.id}`;
  });

  /* ------------------------------------------------------------- soạn tin */
  const input = $("input");
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 130) + "px"; }
  function updateSend() { $("send-btn").disabled = state.sending || !(input.value.trim() || state.pendingFile) || !(active() && active().can_send); }
  function clearAttachment() { state.pendingFile = null; $("attach-slot").replaceChildren(); $("file-input").value = ""; }
  function setAttachment(f) {
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { SC.toast("Tệp quá lớn (tối đa 10 MB).", "error"); return; }
    state.pendingFile = f;
    const chip = el("div", "attach-chip");
    if (f.type.startsWith("image/")) { const i = el("img"); i.src = URL.createObjectURL(f); chip.appendChild(i); } else chip.appendChild(el("span", null, "📄"));
    chip.append(el("span", null, `${f.name} (${SC.fmtSize(f.size)})`), btn("✕", "", () => { clearAttachment(); updateSend(); }));
    $("attach-slot").replaceChildren(chip); updateSend();
  }
  input.addEventListener("input", () => {
    autosize(); updateSend();
    const c = active(); if (!c || !socket || !c.can_send) return;
    const now = Date.now();
    if (input.value && now - state.typingSent > 2500) { socket.emit("typing", { conversation_id: c.id, is_typing: true }); state.typingSent = now; }
    clearTimeout(input._t); input._t = setTimeout(() => { socket.emit("typing", { conversation_id: c.id, is_typing: false }); state.typingSent = 0; }, 3000);
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  $("send-btn").addEventListener("click", send);
  $("attach-btn").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", (e) => setAttachment(e.target.files[0]));
  input.addEventListener("paste", (e) => { const f = [...(e.clipboardData || {}).files || []].find((x) => x.type.startsWith("image/")); if (f) { e.preventDefault(); setAttachment(f); } });
  const panel = $("chat-panel");
  ["dragenter", "dragover"].forEach((ev) => panel.addEventListener(ev, (e) => { if (active() && active().can_send) { e.preventDefault(); panel.classList.add("drag-over"); } }));
  ["dragleave", "drop"].forEach((ev) => panel.addEventListener(ev, (e) => { if (ev === "dragleave" && panel.contains(e.relatedTarget)) return; e.preventDefault(); panel.classList.remove("drag-over"); if (ev === "drop" && active() && active().can_send) setAttachment(e.dataTransfer.files[0]); }));

  // emoji
  const pop = $("emoji-pop");
  EMOJIS.forEach((em) => { const b = el("button", null, em); b.type = "button"; b.addEventListener("click", (e) => { e.stopPropagation(); const s = input.selectionStart ?? input.value.length; input.value = input.value.slice(0, s) + em + input.value.slice(input.selectionEnd ?? s); input.focus(); input.selectionStart = input.selectionEnd = s + em.length; autosize(); updateSend(); }); pop.appendChild(b); });
  $("emoji-btn").addEventListener("click", (e) => { e.stopPropagation(); pop.classList.toggle("hidden"); });
  pop.addEventListener("click", (e) => e.stopPropagation());

  async function send() {
    const c = active(); if (!c || state.sending || !c.can_send) return;
    const body = input.value.trim(), file = state.pendingFile;
    if (!body && !file) return;
    if (body.length > 2000) { SC.toast("Tin nhắn quá dài (tối đa 2000 ký tự).", "error"); return; }
    state.sending = true; updateSend();
    try {
      let d;
      const reply = state.replyTo ? state.replyTo.id : null;
      if (file) { const fd = new FormData(); if (body) fd.append("body", body); fd.append("file", file); if (reply) fd.append("reply_to_id", reply); d = await api("POST", `/api/conversations/${c.id}/messages`, fd); }
      else d = await api("POST", `/api/conversations/${c.id}/messages`, { body, reply_to_id: reply });
      input.value = ""; clearAttachment(); clearReply(); autosize();
      socket && socket.emit("typing", { conversation_id: c.id, is_typing: false }); state.typingSent = 0;
      if (state.activeId === c.id) { upsertMessage(d.message); renderMessages(true); }
    } catch (e) {
      if (e.status !== 401) SC.toast(e.message, "error");
      if (e.status === 403) { await refreshActive(); }
    } finally { state.sending = false; updateSend(); if (!matchMedia("(max-width:860px)").matches) input.focus(); }
  }

  /* ------------------------------------------------------------- tin nhắn thoại */
  const rec = { mr: null, chunks: [], start: 0, timer: null, stream: null, cancel: false };
  function showRec(on) { $("recording").classList.toggle("hidden", !on); $("composer").classList.toggle("hidden", on); }
  async function startRec() {
    const c = active(); if (!c || !c.can_send || rec.mr) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { SC.toast("Trình duyệt không hỗ trợ ghi âm.", "error"); return; }
    try { rec.stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { SC.toast("Không mở được micro. Hãy cho phép trình duyệt dùng micro (cần localhost hoặc HTTPS).", "error"); return; }
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
    rec.mr = new MediaRecorder(rec.stream, type ? { mimeType: type } : undefined); rec.chunks = []; rec.cancel = false;
    const cid = c.id;
    rec.mr.ondataavailable = (e) => { if (e.data && e.data.size) rec.chunks.push(e.data); };
    rec.mr.onstop = () => {
      rec.stream.getTracks().forEach((t) => t.stop()); clearInterval(rec.timer); showRec(false);
      const dur = (Date.now() - rec.start) / 1000, mime = rec.mr.mimeType || "audio/webm", chunks = rec.chunks, cancelled = rec.cancel;
      rec.mr = null;
      if (cancelled) return;
      if (dur < 1) { SC.toast("Tin nhắn thoại quá ngắn.", ""); return; }
      const ext = mime.includes("ogg") ? "ogg" : mime.includes("mp4") ? "m4a" : "webm";
      sendVoice(cid, new Blob(chunks, { type: mime }), ext, Math.min(dur, VOICE_MAX));
    };
    rec.mr.start(250); rec.start = Date.now(); $("rec-time").textContent = "0:00"; showRec(true);
    rec.timer = setInterval(() => { const s = (Date.now() - rec.start) / 1000; $("rec-time").textContent = fmtDur(s); if (s >= VOICE_MAX) stopRec(false); }, 250);
  }
  function stopRec(cancel) { if (rec.mr && rec.mr.state !== "inactive") { rec.cancel = cancel; rec.mr.stop(); } }
  const sendVoice = guard(async (cid, blob, ext, dur) => {
    const fd = new FormData(); fd.append("voice", blob, `ghi-am.${ext}`); fd.append("duration", dur.toFixed(1));
    if (state.replyTo && state.activeId === cid) fd.append("reply_to_id", state.replyTo.id);
    const d = await api("POST", `/api/conversations/${cid}/messages`, fd);
    if (state.activeId === cid) { clearReply(); upsertMessage(d.message); renderMessages(true); }
  });
  $("mic-btn").addEventListener("click", startRec);
  $("rec-cancel").addEventListener("click", () => stopRec(true));
  $("rec-send").addEventListener("click", () => stopRec(false));

  async function refreshActive() {
    const c = active(); if (!c) return;
    try { setConv((await api("GET", `/api/conversations/${c.id}`, null, { silent: true })).conversation); renderHeader(); renderPinned(); renderBanners(); renderComposerState(); renderList(); } catch (e) { /* bỏ qua */ }
  }

  /* ------------------------------------------------------ cuộn tải tin cũ */
  $("msgs").addEventListener("scroll", async (e) => {
    const box = e.target, c = active();
    nearBottom();
    if (!c || box.scrollTop > 60 || !state.hasMore.get(c.id) || state.loadingOlder) return;
    state.loadingOlder = true;
    try {
      const arr = state.msgs.get(c.id) || [];
      const d = await api("GET", `/api/conversations/${c.id}/messages?before=${arr[0].id}`, null, { silent: true });
      d.messages.forEach(upsertMessage); state.hasMore.set(c.id, d.has_more);
      renderMessages._keep = true; renderMessages(false); renderMessages._keep = false;
    } catch (err) { /* bỏ qua */ } finally { state.loadingOlder = false; }
  });

  function lightbox(url) {
    const lb = el("div", "lightbox"); const i = el("img"); i.src = url; lb.appendChild(i);
    const close = () => { lb.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    lb.addEventListener("click", close); document.addEventListener("keydown", onKey); document.body.appendChild(lb);
  }

  /* ------------------------------------------------------------ socket */
  function setTitle() { const n = [...state.convs.values()].reduce((s, c) => s + (c.unread || 0), 0); document.title = (n ? `(${n}) ` : "") + "Tin nhắn · DangNam"; }
  let typingTimer = null;
  if (socket) {
    socket.on("message:new", (p) => {
      const old = setConv(p.conversation); const m = p.message;
      const isActive = state.activeId === m.conversation_id;
      if (isActive) {
        upsertMessage(m);
        if (!m.mine && !document.hidden) { p.conversation.unread = 0; markRead(); }
        const levelUp = old && p.conversation.warning > old.warning;
        renderHeader(); renderBanners(levelUp); renderMessages(m.mine); renderComposerState();
        if (!m.mine) { $("typing").textContent = ""; }
      } else if (!m.mine) {
        SC.toast(`💬 ${SC.displayName(p.conversation.other)}: ${p.conversation.last_message ? p.conversation.last_message.preview.slice(0, 80) : ""}`);
      }
      if (!m.mine && p.conversation.warning > 0 && (!old || p.conversation.warning > old.warning) && !isActive)
        SC.toast(`${p.conversation.warning >= 3 ? "🚨" : "⚠️"} ${SC.displayName(p.conversation.other)} gửi tin có dấu hiệu lừa đảo`, "error");
      renderList(); setTitle();
    });
    // Vệ sĩ phân tích xong (chạy nền) -> cập nhật huy hiệu + thẻ giải thích. CHỈ người nhận nhận được sự kiện này.
    socket.on("guardian:message", (p) => {
      const old = setConv(p.conversation); const m = p.message;
      const isActive = state.activeId === m.conversation_id;
      if (isActive) {
        upsertMessage(m);
        const levelUp = old && p.conversation.warning > old.warning;
        renderBanners(levelUp); renderMessages(nearBottom());
      } else if (m.warning_level >= 2) SC.toast(`${m.warning_level >= 3 ? "⛔" : "🚨"} ${SC.displayName(p.conversation.other)} gửi tin có dấu hiệu lừa đảo`, "error");
      renderList();
    });
    socket.on("appeal:update", () => { loadConversations(); refreshActive(); loadBlocked(); });
    // Thu hồi / thả cảm xúc / ghim: cập nhật lại tin (và các trích dẫn tới tin đó)
    socket.on("message:update", (p) => {
      setConv(p.conversation); const m = p.message, arr = state.msgs.get(m.conversation_id);
      if (arr) {
        const i = arr.findIndex((x) => x.id === m.id); if (i >= 0) arr[i] = m;
        if (m.recalled) arr.forEach((x) => { if (x.reply_to && x.reply_to.id === m.id) x.reply_to.preview = "Tin nhắn đã bị thu hồi"; });
      }
      if (state.activeId === m.conversation_id) { renderPinned(); renderMessages(false); }
      renderList();
    });
    socket.on("message:status", (p) => {
      const arr = state.msgs.get(p.conversation_id); if (!arr) return;
      arr.forEach((m) => { if (p.message_ids.includes(m.id)) { if (p.status === "seen") { m.read_at = p.at; m.delivered_at = m.delivered_at || p.at; } else m.delivered_at = m.delivered_at || p.at; } });
      if (state.activeId === p.conversation_id) renderMessages(false);
    });
    socket.on("conversation:read", (p) => { const c = state.convs.get(p.conversation_id); if (c) { c.unread = 0; renderList(); setTitle(); } });
    socket.on("typing", (p) => {
      if (p.conversation_id !== state.activeId) return;
      const t = $("typing"); clearTimeout(typingTimer);
      if (!p.is_typing) { t.textContent = ""; return; }
      const c = active(); t.replaceChildren(document.createTextNode(`${SC.displayName(c.other)} đang nhập`), (() => { const d = el("span", "dots"); d.innerHTML = "<span>.</span><span>.</span><span>.</span>"; return d; })());
      typingTimer = setTimeout(() => (t.textContent = ""), 4500);
      if (nearBottom()) scrollBottom();
    });
    socket.on("presence", (p) => {
      state.convs.forEach((c) => { if (c.other.id === p.user_id) { c.other.online = p.online; c.other.last_seen = p.last_seen || c.other.last_seen; } });
      state.friends.forEach((u) => { if (u.id === p.user_id) u.online = p.online; });
      if (active() && active().other.id === p.user_id) renderHeader();
      renderList();
    });
    socket.on("friend:update", () => afterSocial());
    socket.on("block:update", async () => { await afterSocial(); await refreshActive(); });
    socket.on("connect", async () => { if (state.firstConnect) { state.firstConnect = false; return; } await loadConversations(); const c = active(); if (c) { const h = await api("GET", `/api/conversations/${c.id}/messages`, null, { silent: true }).catch(() => null); if (h) { state.msgs.set(c.id, h.messages); state.hasMore.set(c.id, h.has_more); renderMessages(true); renderBanners(); renderComposerState(); markRead(); } } });
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) markRead(); });
  window.addEventListener("focus", markRead);
  setInterval(() => { const c = active(); if (c && !c.other.online && c.other.last_seen) $("head-status").textContent = statusText(c); }, 60000);

  /* ---------------------------------------------------------- khởi động */
  (async function init() {
    await Promise.all([loadConversations(), loadRequests(), loadFriends(), loadBlocked()]);
    setTitle();
    const initial = parseInt(layout.dataset.initialCid, 10);
    if (initial) await openConversation(initial);
  })();
})();
