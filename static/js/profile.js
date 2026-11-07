/* Trang cá nhân: đổi ảnh đại diện / ảnh bìa, sửa thông tin, nút kết bạn / nhắn tin / gọi, Thẻ tín nhiệm */
(function () {
  "use strict";
  const SC = window.SC; const page = document.getElementById("profile-page"); if (!SC || !page) return;
  const { api, el, toast } = SC;
  const data = JSON.parse(document.getElementById("profile-data").textContent);
  const u = data.user;
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };

  if (data.is_me) {
    const upload = (kind) => guard(async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      const d = await api("POST", `/api/profile/${kind}`, fd);
      if (kind === "cover") document.getElementById("cover").style.backgroundImage = `url('${d.cover}')`;
      else document.getElementById("hero-avatar").replaceChildren(SC.avatar(d.user, "hero"));
      toast(kind === "cover" ? "Đã đổi ảnh bìa" : "Đã đổi ảnh đại diện", "ok");
    });
    document.getElementById("avatar-input").addEventListener("change", upload("avatar"));
    document.getElementById("cover-input").addEventListener("change", upload("cover"));
    document.getElementById("edit-profile").addEventListener("click", guard(async () => {
      const box = el("div", "form-grid");
      const name = el("input", "input"); name.value = u.name; name.maxLength = 80; name.placeholder = "Họ và tên";
      const bio = el("textarea", "input"); bio.value = u.bio || ""; bio.maxLength = 300; bio.rows = 3; bio.placeholder = "Giới thiệu";
      const by = el("input", "input"); by.type = "number"; by.min = 1900; by.max = 2025; by.value = u.birth_year || ""; by.placeholder = "Năm sinh";
      [["Họ và tên", name], ["Giới thiệu", bio], ["Năm sinh", by]].forEach(([l, i]) => { const lb = el("label", null, l); lb.appendChild(i); box.appendChild(lb); });
      box.appendChild(el("p", "muted small", "Lịch sử đổi tên được lưu lại để Vệ sĩ phát hiện tài khoản giả mạo."));
      if (!(await SC.dialog({ title: "Chỉnh sửa trang cá nhân", ok: "Lưu", body: box }))) return;
      await api("POST", "/api/profile", { display_name: name.value, bio: bio.value, birth_year: by.value ? parseInt(by.value, 10) : null });
      location.reload();
    }));
    return;
  }

  // Người khác: nút quan hệ + nhắn tin + gọi
  const actions = document.getElementById("hero-actions");
  const rel = data.relation || {};
  const person = { ...u, relation: rel.status, request_id: rel.request_id, i_blocked: rel.i_blocked };
  actions.appendChild(SC.relationButtons(person, () => location.reload()));
  if (!rel.i_blocked && SC.startCall) {
    const call = (video) => guard(async () => { const d = await api("POST", "/api/conversations", { user_id: u.id }); SC.startCall(d.conversation.id, video); });
    const a = el("button", "btn btn-sm", "📞 Gọi thoại"); a.addEventListener("click", call(false));
    const v = el("button", "btn btn-sm", "🎥 Gọi video"); v.addEventListener("click", call(true));
    actions.append(a, v);
  }
})();
