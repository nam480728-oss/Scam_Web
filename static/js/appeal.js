/* Khiếu nại gỡ chặn: chụp trực tiếp 3 khung (thao tác ngẫu nhiên, kiểm tra có mặt + có cử động) → Mật mã gia đình → 2 bên xác nhận nhau */
(function () {
  "use strict";
  const SC = window.SC; const page = document.getElementById("appeal-page"); if (!SC || !page) return;
  const { api, el, toast } = SC;
  const $ = (id) => document.getElementById(id);
  const aid = parseInt(page.dataset.id, 10);
  let st = null, stream = null, busy = false;
  const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { if (e.status !== 401) toast(e.message, "error"); } };
  const STATUS = { open: ["🕓 Đang xác minh", "warn"], success: ["✅ Thành công · đã gỡ chặn", "ok"], failed: ["❌ Thất bại · vẫn chặn", "danger"], expired: ["⌛ Hết hạn · vẫn chặn", "danger"] };

  /* ------------------------------------------------------------ hiển thị */
  function render() {
    const s = st, steps = s.steps, open = s.status === "open";
    const head = $("ap-head"); head.replaceChildren();
    const top = el("div", "ap-top"); top.appendChild(SC.avatar(s.other, "lg"));
    const info = el("div");
    info.appendChild(el("h1", null, "🛡️ Khiếu nại gỡ chặn"));
    info.appendChild(el("div", null, s.role === "protected"
      ? `Vệ sĩ đã tự động chặn ${SC.displayName(s.other)} sau 3 lần phát hiện tin lừa đảo. Nếu đây là người thân / người quen của bạn, hãy cùng xác minh để gỡ chặn.`
      : `Hệ thống đã chặn bạn nhắn tin với ${SC.displayName(s.other)}. Hãy cùng ${SC.displayName(s.other)} xác minh để chứng minh đây là nhầm lẫn.`));
    const [txt, cls] = STATUS[s.status] || [s.status, ""];
    const meta = el("div", "ap-meta"); meta.append(el("span", "pill " + cls, txt));
    if (open) meta.appendChild(el("span", "pill", "Hạn chót: " + SC.fmtFull(s.expires_at)));
    info.appendChild(meta); top.appendChild(info); head.appendChild(top);
    // tiến độ 2 bên
    const prog = el("div", "ap-progress");
    const row = (who, cap, conf) => { const r = el("div", "ap-prog-row"); r.append(el("b", null, who), el("span", cap ? "ok" : "", cap ? "✓ đã chụp xác minh" : "… chưa chụp"),
      el("span", conf === true ? "ok" : conf === false ? "bad" : "", conf === true ? "✓ đã xác nhận" : conf === false ? "✗ từ chối" : "… chưa xác nhận")); return r; };
    prog.append(row("Bạn", steps.my_capture.done, steps.my_confirm), row(SC.displayName(s.other), steps.other_capture.done, steps.other_confirm));
    if (steps.question.required) prog.appendChild(el("div", steps.question.passed ? "ok small" : "small",
      `Mật mã gia đình: ${steps.question.passed ? "✓ đã trả lời đúng" : `chưa đúng (${steps.question.attempts}/${steps.question.max} lần thử)`}`));
    head.appendChild(prog);

    const res = $("ap-result");
    res.classList.toggle("hidden", open);
    if (!open) {
      res.replaceChildren(el("h2", null, txt));
      if (s.fail_reason) res.appendChild(el("p", null, "Lý do: " + s.fail_reason));
      if (s.status === "success") {
        res.appendChild(el("p", null, "Hai bạn đã nhắn tin, gọi điện lại được. Ảnh xác minh đã được xóa."));
        res.appendChild(el("p", "muted", "🛡️ Vệ sĩ vẫn theo dõi lại từ đầu: nếu lại phát hiện lừa đảo thì cảnh báo lần 1 → lần 2 (che tin) → lần 3 tự động chặn lại."));
      }
      else res.appendChild(el("p", "muted", "Ảnh xác minh đã được xóa. Bạn có thể gửi khiếu nại mới từ khung chat (nếu còn lượt)."));
      const a = el("a", "btn btn-primary", "← Về tin nhắn"); a.href = s.conversation_id ? `/messages/${s.conversation_id}` : "/messages"; res.appendChild(a);
    }
    ["step-capture", "step-question", "step-confirm"].forEach((id) => $(id).classList.toggle("hidden", !open));
    if (!open) { stopCam(); return; }
    renderCapture(); renderQuestion(); renderConfirm();
  }

  function renderCapture() {
    const c = st.steps.my_capture, msg = $("ap-capture-msg");
    if (c.done) {
      stopCam(); $("ap-shoot").classList.add("hidden");
      $("ap-video").closest(".ap-cam").classList.add("hidden");
      msg.replaceChildren(el("div", "notice ok", "✅ Đã chụp xác minh: thấy rõ khuôn mặt và cử động."));
      return;
    }
    $("ap-shoot").textContent = c.tries ? `📸 Chụp lại (lần ${c.tries + 1}/${c.max_tries})` : "📸 Bắt đầu chụp xác minh";
    startCam();
  }

  function renderQuestion() {
    const q = st.steps.question, box = $("ap-question");
    $("step-question").classList.toggle("hidden", !q.required);
    $("ap-confirm-num").textContent = q.required ? "3" : "2";
    if (!q.required) return;
    box.replaceChildren();
    if (q.passed) { box.appendChild(el("div", "notice ok", "✅ Đã trả lời đúng Mật mã gia đình.")); return; }
    if (!q.i_answer) { box.appendChild(el("p", null, `${SC.displayName(st.other)} cần trả lời câu hỏi bí mật bạn đã đặt trong Cài đặt (đã thử ${q.attempts}/${q.max} lần).`)); return; }
    box.appendChild(el("p", null, "Người được bảo vệ đã đặt câu hỏi bí mật. Chỉ người thân thật mới biết đáp án:"));
    box.appendChild(el("p", "fq", `“${q.text}”`));
    const f = el("form", "form-row"); const inp = el("input", "input"); inp.placeholder = "Câu trả lời"; inp.maxLength = 100; inp.autocomplete = "off";
    const b = el("button", "btn btn-primary", "Gửi câu trả lời"); f.append(inp, b);
    f.addEventListener("submit", guard(async (e) => {
      e.preventDefault(); if (!inp.value.trim()) return;
      const r = await api("POST", `/api/appeals/${aid}/answer`, { answer: inp.value });
      toast(r.correct ? "✅ Trả lời đúng" : `❌ Sai (${r.attempts}/${q.max})`, r.correct ? "ok" : "error"); st = r.appeal; render();
    }));
    box.appendChild(f); box.appendChild(el("small", "muted", `Còn ${q.max - q.attempts} lần thử. Sai ${q.max} lần thì khiếu nại thất bại.`));
  }

  function renderConfirm() {
    const box = $("ap-confirm"), s = st.steps; box.replaceChildren();
    if (!s.my_capture.done || !s.other_capture.done) {
      box.appendChild(el("p", "muted", "Khi cả hai bên đã chụp xác minh xong, ảnh của bên kia sẽ hiện ở đây để bạn xác nhận."));
      return;
    }
    box.appendChild(el("p", null, `Ảnh chụp trực tiếp của ${SC.displayName(st.other)}. Hãy nhìn kỹ: đây có đúng là người thân / người quen của bạn?`));
    const g = el("div", "ap-photos"); st.other_photos.forEach((u) => { const i = el("img"); i.src = u + "?t=" + Date.now(); i.alt = "Ảnh xác minh"; g.appendChild(i); });
    box.appendChild(g);
    if (s.my_confirm === true) { box.appendChild(el("div", "notice ok", "✓ Bạn đã xác nhận. Đang chờ bên kia…")); return; }
    const acts = el("div", "gc-actions");
    const yes = el("button", "btn btn-primary", "✅ Đúng là người thân / người quen của tôi");
    const no = el("button", "btn btn-danger", "❌ Không phải người tôi biết");
    yes.onclick = guard(async () => { st = (await api("POST", `/api/appeals/${aid}/confirm`, { accept: true })).appeal; render(); });
    no.onclick = guard(async () => {
      if (!(await SC.dialog({ title: "Xác nhận KHÔNG phải người quen?", text: "Khiếu nại sẽ thất bại và giữ nguyên việc chặn.", danger: true, ok: "Đúng, không phải" }))) return;
      st = (await api("POST", `/api/appeals/${aid}/confirm`, { accept: false })).appeal; render();
    });
    acts.append(yes, no); box.appendChild(acts);
  }

  /* ------------------------------------------------------------ camera */
  async function startCam() {
    if (stream) return;
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false }); $("ap-video").srcObject = stream; }
    catch (e) { $("ap-capture-msg").replaceChildren(el("div", "notice danger", "Không mở được camera. Hãy cho phép trình duyệt dùng camera (cần localhost hoặc HTTPS).")); }
  }
  function stopCam() { if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; } }
  const grab = () => new Promise((res) => {
    const v = $("ap-video"), c = $("ap-canvas"); const w = v.videoWidth || 640, h = v.videoHeight || 480;
    c.width = w; c.height = h; c.getContext("2d").drawImage(v, 0, 0, w, h); c.toBlob(res, "image/jpeg", 0.9);
  });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  $("ap-shoot").addEventListener("click", guard(async () => {
    if (busy) return; busy = true; $("ap-shoot").disabled = true;
    try {
      const ch = await api("POST", `/api/appeals/${aid}/challenge`);
      const act = $("ap-action"), cnt = $("ap-count");
      act.textContent = "👉 " + ch.action; act.classList.remove("hidden");
      for (const n of [3, 2, 1]) { cnt.textContent = n; cnt.classList.remove("hidden"); await sleep(800); }
      cnt.textContent = "📸"; const frames = [];
      for (let i = 0; i < ch.frames; i++) { frames.push(await grab()); await sleep(1000); }     // 3 khung trong ~3 giây, đang làm thao tác
      cnt.classList.add("hidden"); act.classList.add("hidden");
      const fd = new FormData(); fd.append("nonce", ch.nonce);
      frames.forEach((b, i) => fd.append(`frame${i}`, b, `frame${i}.jpg`));
      $("ap-capture-msg").replaceChildren(el("div", "notice", "🛡️ Vệ sĩ đang kiểm tra hình ảnh…"));
      const r = await api("POST", `/api/appeals/${aid}/capture`, fd);
      st = r.appeal;
      if (r.passed) toast("✅ Chụp xác minh thành công", "ok");
      else $("ap-capture-msg").replaceChildren(el("div", "notice danger", "❌ " + r.reason));
      render();
      if (!r.passed && st.status === "open") $("ap-capture-msg").replaceChildren(el("div", "notice danger", "❌ " + r.reason));
    } finally { busy = false; $("ap-shoot").disabled = false; }
  }));

  /* ------------------------------------------------------------ khởi động */
  const load = guard(async () => { st = (await api("GET", `/api/appeals/${aid}`)).appeal; render(); });
  if (SC.socket) SC.socket.on("appeal:update", (p) => { if (p.appeal_id === aid) load(); });
  window.addEventListener("beforeunload", stopCam);
  load();
})();
