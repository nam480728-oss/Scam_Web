/* Mạng xã hội: bài đăng (cảm xúc, bình luận, chia sẻ), ô đăng bài, nút kết bạn, trang Bạn bè / Tìm kiếm / Hồ sơ */
(function () {
  "use strict";
  const SC = window.SC; if (!SC || !SC.me) return;
  const { api, el, avatar, toast } = SC;
  const $ = (id) => document.getElementById(id);
  const REACTIONS = [["like", "👍", "Thích"], ["love", "❤️", "Yêu thích"], ["haha", "😆", "Haha"], ["sad", "😢", "Buồn"], ["angry", "😡", "Phẫn nộ"]];
  const RMAP = Object.fromEntries(REACTIONS.map(([k, e, l]) => [k, { e, l }]));
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };
  const btn = (label, cls, fn) => { const b = el("button", "btn btn-sm " + (cls || ""), label); b.type = "button"; b.addEventListener("click", (e) => { e.stopPropagation(); fn(b); }); return b; };

  /* ----------------------------------------------------------------- bài đăng */
  function authorLink(u) {
    const a = el("a", "author"); if (u.username) a.href = `/u/${encodeURIComponent(u.username)}`;
    a.appendChild(document.createTextNode(u.name)); a.appendChild(SC.badges(u)); return a;
  }
  function postHead(p) {
    const h = el("header", "post-head");
    const av = avatar(p.author, ""); if (p.author.username) { const a = el("a"); a.href = `/u/${encodeURIComponent(p.author.username)}`; a.appendChild(av); h.appendChild(a); } else h.appendChild(av);
    const who = el("div", "who"); who.appendChild(authorLink(p.author));
    const small = el("small", null, (p.fake ? p.ago : SC.fmtAgo(p.created_at)) + " · 🌐"); if (!p.fake) small.title = SC.fmtFull(p.created_at);
    if (p.fake) small.appendChild(el("span", "pill", "mô phỏng"));
    who.appendChild(small); h.appendChild(who);
    if (p.mine) {
      const m = btn("🗑", "ghost", guard(async () => {
        if (!(await SC.dialog({ title: "Xóa bài viết?", text: "Bài viết sẽ bị xóa vĩnh viễn.", ok: "Xóa", danger: true }))) return;
        await api("DELETE", `/api/posts/${p.id}`); h.closest(".post").remove();
      })); m.title = "Xóa bài viết"; h.appendChild(m);
    }
    return h;
  }
  function bodyNode(text) { const d = el("div", "post-body"); d.textContent = text; return d; }

  function renderPost(p) {
    const art = el("article", "post" + (p.warn ? " warn" : "")); art.dataset.id = p.id;
    art.appendChild(postHead(p));
    if (p.body) art.appendChild(bodyNode(p.body));
    if (p.image) { const i = el("img", "post-img"); i.src = p.image; i.alt = "Ảnh bài viết"; i.loading = "lazy"; art.appendChild(i); }
    if (p.shared) {
      const box = el("div", "shared-box");
      if (p.shared.deleted) box.appendChild(el("div", "muted", "Bài viết gốc đã bị xóa."));
      else { box.appendChild(postHead({ ...p.shared, mine: false })); if (p.shared.body) box.appendChild(bodyNode(p.shared.body));
        if (p.shared.image) { const i = el("img", "post-img"); i.src = p.shared.image; i.loading = "lazy"; box.appendChild(i); } }
      art.appendChild(box);
    }
    if (p.fake) {
      const st = el("div", "post-stats"); st.append(el("span", null, `👍❤️ ${p.likes.toLocaleString("vi-VN")}`), el("span", null, `${p.comments} bình luận · ${p.shares} lượt chia sẻ`));
      art.appendChild(st);
      const ac = el("div", "post-actions"); ["👍 Thích", "💬 Bình luận", "↪ Chia sẻ"].forEach((t) => ac.appendChild(el("span", "dim", t))); art.appendChild(ac);
      return art;
    }
    const stats = el("div", "post-stats"); art.appendChild(stats);
    const actions = el("div", "post-actions"); art.appendChild(actions);
    const comments = el("div", "comments hidden"); art.appendChild(comments);
    const state = { r: p.reactions, comments: p.comments, shares: p.shares, loaded: false };
    const drawStats = () => {
      stats.replaceChildren(el("span", null, state.r.total ? `${state.r.top.join("")} ${state.r.total}` : ""),
        el("span", null, `${state.comments} bình luận · ${state.shares} lượt chia sẻ`));
      const mine = state.r.mine ? RMAP[state.r.mine] : null;
      likeBtn.textContent = mine ? `${mine.e} ${mine.l}` : "👍 Thích"; likeBtn.classList.toggle("on", !!mine);
    };
    const setReact = guard(async (kind) => { const d = await api("POST", `/api/posts/${p.id}/react`, { kind }); state.r = d.reactions; drawStats(); });
    const likeWrap = el("div", "react-wrap");
    const likeBtn = el("button", "act"); likeBtn.type = "button";
    likeBtn.addEventListener("click", () => setReact(state.r.mine ? null : "like"));
    const picker = el("div", "react-picker");
    REACTIONS.forEach(([k, e, l]) => { const b = el("button", null, e); b.type = "button"; b.title = l; b.addEventListener("click", (ev) => { ev.stopPropagation(); setReact(k); }); picker.appendChild(b); });
    likeWrap.append(likeBtn, picker);
    const cBtn = el("button", "act", "💬 Bình luận"); cBtn.type = "button";
    cBtn.addEventListener("click", guard(async () => {
      comments.classList.toggle("hidden");
      if (!state.loaded) { state.loaded = true; drawComments((await api("GET", `/api/posts/${p.id}/comments`)).comments); }
      const inp = comments.querySelector("input"); if (inp) inp.focus();
    }));
    const sBtn = el("button", "act", "↪ Chia sẻ"); sBtn.type = "button";
    sBtn.addEventListener("click", guard(async () => {
      const ta = el("textarea", "input"); ta.placeholder = "Hãy nói gì đó về nội dung này (không bắt buộc)"; ta.rows = 3; ta.maxLength = 5000;
      if (!(await SC.dialog({ title: "Chia sẻ lên bảng tin của bạn", ok: "Chia sẻ ngay", body: ta }))) return;
      const d = await api("POST", `/api/posts/${p.shared && !p.shared.deleted ? p.shared.id : p.id}/share`, { body: ta.value });
      state.shares += 1; drawStats(); toast("Đã chia sẻ bài viết", "ok");
      const feed = $("posts"); if (feed && feed.dataset.prepend) feed.prepend(renderPost(d.post));
    }));
    actions.append(likeWrap, cBtn, sBtn);
    function drawComments(list) {
      comments.replaceChildren();
      list.forEach((c) => comments.appendChild(commentNode(c)));
      const f = el("form", "comment-form"); const inp = el("input", "input"); inp.placeholder = "Viết bình luận…"; inp.maxLength = 1000;
      f.append(avatar(SC.me, "sm"), inp);
      f.addEventListener("submit", guard(async (e) => {
        e.preventDefault(); const body = inp.value.trim(); if (!body) return;
        const d = await api("POST", `/api/posts/${p.id}/comments`, { body }); inp.value = "";
        f.before(commentNode(d.comment)); state.comments += 1; drawStats();
      }));
      comments.appendChild(f);
    }
    drawStats();
    return art;
  }
  function commentNode(c) {
    const r = el("div", "comment"); r.appendChild(avatar(c.author, "sm"));
    const b = el("div", "cbubble"); b.appendChild(authorLink(c.author)); b.appendChild(el("div", null, c.body));
    const wrap = el("div"); wrap.append(b, el("small", "muted", SC.fmtAgo(c.created_at))); r.appendChild(wrap); return r;
  }
  SC.renderPost = renderPost;

  const postsBox = $("posts");
  if (postsBox) {
    const data = JSON.parse(($("posts-data") || {}).textContent || "[]");
    if (!data.length) postsBox.appendChild(el("div", "feed-note", "Chưa có bài viết nào."));
    data.forEach((p) => postsBox.appendChild(renderPost(p)));
  }

  /* ----------------------------------------------------------------- ô đăng bài */
  const composer = $("composer");
  if (composer) {
    const ta = composer.querySelector("textarea"), file = composer.querySelector("input[type=file]"), prev = $("composer-preview");
    file.addEventListener("change", () => {
      prev.replaceChildren(); const f = file.files[0]; if (!f) return;
      if (f.size > 10 * 1024 * 1024) { toast("Ảnh quá lớn (tối đa 10 MB).", "error"); file.value = ""; return; }
      const i = el("img"); i.src = URL.createObjectURL(f); prev.append(i, btn("✕", "", () => { file.value = ""; prev.replaceChildren(); }));
    });
    composer.addEventListener("submit", guard(async (e) => {
      e.preventDefault();
      if (!ta.value.trim() && !file.files[0]) return;
      const fd = new FormData(); fd.append("body", ta.value); if (file.files[0]) fd.append("image", file.files[0]);
      const b = composer.querySelector("button[type=submit]"); b.disabled = true;
      try { const d = await api("POST", "/api/posts", fd); ta.value = ""; file.value = ""; prev.replaceChildren(); postsBox.prepend(renderPost(d.post)); toast("Đã đăng bài", "ok"); }
      finally { b.disabled = false; }
    }));
  }

  /* --------------------------------------------------------- nút quan hệ bạn bè */
  // Dựng các nút theo quan hệ: none | sent | received | friend (dùng ở Hồ sơ, Tìm kiếm, Gợi ý)
  function relationButtons(u, onChange) {
    const box = el("div", "rel-btns");
    const redo = async () => { if (onChange) await onChange(); };
    const add = guard(async () => { await api("POST", "/api/friend-requests", { user_id: u.id }); toast(`Đã gửi lời mời tới ${u.name}`, "ok"); u.relation = "sent"; draw(); redo(); });
    const draw = () => {
      box.replaceChildren();
      if (u.i_blocked) { box.appendChild(btn("Bỏ chặn", "", guard(async () => { await api("DELETE", `/api/blocks/${u.id}`); u.i_blocked = false; draw(); redo(); }))); return; }
      if (u.relation === "friend") box.appendChild(el("span", "pill ok", "✓ Bạn bè"));
      else if (u.relation === "sent") box.appendChild(btn("Hủy lời mời", "", guard(async () => { await api("DELETE", `/api/friend-requests/${u.request_id}`); u.relation = "none"; draw(); redo(); })));
      else if (u.relation === "received") {
        box.appendChild(btn("Chấp nhận", "btn-primary", guard(async () => { await api("POST", `/api/friend-requests/${u.request_id}/accept`); u.relation = "friend"; draw(); redo(); })));
        box.appendChild(btn("Từ chối", "", guard(async () => { await api("POST", `/api/friend-requests/${u.request_id}/decline`); u.relation = "none"; draw(); redo(); })));
      } else box.appendChild(btn("➕ Kết bạn", "btn-primary", add));
      box.appendChild(btn("💬 Nhắn tin", "", guard(async () => { const d = await api("POST", "/api/conversations", { user_id: u.id }); location.href = `/messages/${d.conversation.id}`; })));
    };
    draw();
    return box;
  }
  SC.relationButtons = relationButtons;

  function personCard(u, extra) {
    const c = el("div", "person-card");
    const a = el("a", "pc-top"); a.href = `/u/${encodeURIComponent(u.username)}`;
    a.appendChild(avatar(u, "xl"));
    const n = el("b"); n.appendChild(document.createTextNode(u.name)); n.appendChild(SC.badges(u)); a.appendChild(n);
    a.appendChild(el("small", "muted", u.mutual ? `${u.mutual} bạn chung` : "@" + u.username));
    if (u.reputation) a.appendChild(SC.repBadge(u.reputation));
    c.appendChild(a);
    if (extra) c.appendChild(extra);
    return c;
  }
  SC.personCard = personCard;

  /* --------------------------------------------------------------- trang Bạn bè */
  const friendsPage = $("friends-page");
  if (friendsPage) {
    const load = guard(async () => {
      const [req, sug, fr] = await Promise.all([api("GET", "/api/friend-requests"), api("GET", "/api/friends/suggestions"), api("GET", "/api/friends")]);
      const inc = $("fr-incoming"); inc.replaceChildren();
      if (!req.incoming.length) inc.appendChild(el("div", "empty", "Không có lời mời nào."));
      req.incoming.forEach((r) => {
        const extra = el("div", "pc-actions");
        extra.appendChild(btn("Chấp nhận", "btn-primary", guard(async () => { await api("POST", `/api/friend-requests/${r.id}/accept`); toast("Đã trở thành bạn bè 🎉", "ok"); load(); })));
        extra.appendChild(btn("Xóa", "", guard(async () => { await api("POST", `/api/friend-requests/${r.id}/decline`); load(); })));
        inc.appendChild(personCard({ ...r.user, mutual: r.mutual, reputation: r.reputation }, extra));
      });
      const out = $("fr-outgoing"); out.replaceChildren();
      req.outgoing.forEach((r) => out.appendChild(personCard(r.user, btn("Hủy lời mời", "", guard(async () => { await api("DELETE", `/api/friend-requests/${r.id}`); load(); })))));
      $("fr-outgoing-wrap").classList.toggle("hidden", !req.outgoing.length);
      const sg = $("fr-suggest"); sg.replaceChildren();
      if (!sug.users.length) sg.appendChild(el("div", "empty", "Chưa có gợi ý."));
      sug.users.forEach((u) => sg.appendChild(personCard(u, relationButtons({ ...u, relation: "none" }, load))));
      const all = $("fr-all"); all.replaceChildren();
      if (!fr.friends.length) all.appendChild(el("div", "empty", "Chưa có bạn bè."));
      fr.friends.forEach((u) => all.appendChild(personCard(u, null)));
      $("fr-count").textContent = fr.friends.length;
    });
    load();
    if (SC.socket) SC.socket.on("friend:update", load);
  }

  /* --------------------------------------------------------------- tìm kiếm */
  const searchBox = $("search-results");
  if (searchBox) {
    const data = JSON.parse(($("search-data") || {}).textContent || "[]");
    if (!data.length) searchBox.appendChild(el("div", "empty", "Không tìm thấy người dùng nào."));
    data.forEach((u) => searchBox.appendChild(personCard(u, relationButtons(u))));
  }
})();
