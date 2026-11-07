/* Trang Cài đặt: giao diện, bật/tắt AI 3, xác minh giả lập, Mật mã gia đình, người giám hộ */
(function () {
  "use strict";
  const SC = window.SC; const page = document.getElementById("settings-page"); if (!SC || !page) return;
  const { api, el, toast } = SC;
  let st = JSON.parse(document.getElementById("settings-data").textContent);
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };

  function draw() {
    page.querySelectorAll(".switch").forEach((s) => {
      const k = s.dataset.key;
      s.checked = k === "dark_mode" ? st.dark_mode : st.agents[k.replace("_enabled", "")];
    });
    document.getElementById("phone-state").textContent = st.phone ? (st.phone_verified ? `✅ ${st.phone} đã xác minh` : `${st.phone} · chưa xác minh`) : "Chưa có số điện thoại";
    document.getElementById("id-state").textContent = st.identity_verified ? "✅ Đã xác minh, hồ sơ có huy hiệu ✔" : "Chưa xác minh";
    document.getElementById("verify-id").classList.toggle("hidden", st.identity_verified);
    const f = document.getElementById("family-form");
    f.question.value = st.family.question || "";
    document.getElementById("answer-state").textContent = st.family.has_answer ? "(đã đặt)" : "(chưa đặt)";
    const chosen = new Map(st.family.members.map((m) => [m.id, m.relation || ""]));
    const box = document.getElementById("family-members"); box.replaceChildren();
    if (!st.friends.length) box.appendChild(el("div", "muted small", "Hãy kết bạn với người thân trước."));
    st.friends.forEach((u) => {
      const row = el("label", "check-row");
      const cb = el("input"); cb.type = "checkbox"; cb.value = u.id; cb.checked = chosen.has(u.id);
      const rel = el("input", "input sm"); rel.placeholder = "Quan hệ (con, cháu…)"; rel.maxLength = 40; rel.value = chosen.get(u.id) || ""; rel.dataset.for = u.id;
      row.append(cb, SC.avatar(u, "sm"), el("span", null, u.name), rel); box.appendChild(row);
    });
    const sel = document.getElementById("guardian-select"); sel.replaceChildren();
    const none = el("option", null, "— Không có người giám hộ —"); none.value = ""; sel.appendChild(none);
    st.friends.forEach((u) => { const o = el("option", null, u.name); o.value = u.id; if (st.guardian && st.guardian.id === u.id) o.selected = true; sel.appendChild(o); });
    document.getElementById("wards").textContent = st.wards.length ? `Bạn đang là người giám hộ của: ${st.wards.map((w) => w.name).join(", ")}` : "";
  }

  page.querySelectorAll(".switch").forEach((s) => s.addEventListener("change", guard(async () => {
    st = await api("POST", "/api/settings", { [s.dataset.key]: s.checked });
    if (s.dataset.key === "dark_mode") document.documentElement.dataset.theme = s.checked ? "dark" : "light";
    else toast(s.checked ? "Đã bật Vệ sĩ đọc tin nhắn" : "Đã tắt Vệ sĩ đọc tin nhắn", s.checked ? "ok" : "");
    draw();
  })));

  document.getElementById("verify-id").addEventListener("click", guard(async () => {
    const box = el("div", "form-grid");
    const name = el("input", "input"); name.placeholder = "Họ và tên trên CCCD"; name.value = SC.me.name;
    const num = el("input", "input"); num.placeholder = "Số CCCD (12 chữ số)"; num.inputMode = "numeric"; num.maxLength = 12;
    box.append(el("p", "muted small", "Đây là eKYC giả lập để trình diễn. Số CCCD chỉ được kiểm tra định dạng và KHÔNG được lưu lại."), name, num);
    if (!(await SC.dialog({ title: "🪪 Xác minh danh tính", ok: "Xác minh", body: box }))) return;
    st = await api("POST", "/api/settings/verify-identity", { full_name: name.value, id_number: num.value });
    toast("Đã xác minh danh tính ✔", "ok"); draw();
  }));

  document.getElementById("family-form").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const f = e.target;
    const members = [...document.querySelectorAll("#family-members input[type=checkbox]:checked")].map((cb) => ({
      user_id: parseInt(cb.value, 10), relation: document.querySelector(`#family-members input[data-for="${cb.value}"]`).value }));
    st = await api("POST", "/api/settings/family", { question: f.question.value, answer: f.answer.value, members });
    f.answer.value = ""; toast("Đã lưu Mật mã gia đình", "ok"); draw();
  }));

  document.getElementById("guardian-save").addEventListener("click", guard(async () => {
    const v = document.getElementById("guardian-select").value;
    st = await api("POST", "/api/settings/guardian", { user_id: v ? parseInt(v, 10) : null });
    toast("Đã lưu người giám hộ", "ok"); draw();
  }));
  draw();
})();
