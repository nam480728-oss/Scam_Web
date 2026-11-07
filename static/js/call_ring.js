/* Cuộc gọi trên mọi trang: SC.startCall() mở cửa sổ gọi đi; màn hình cuộc gọi đến (nghe / từ chối). */
(function () {
  "use strict";
  const SC = window.SC; if (!SC || !SC.me) return;
  const { el } = SC;

  SC.startCall = function (convId, video) {
    const url = `/call/new?conv=${convId}&video=${video ? 1 : 0}`;
    const w = window.open(url, `dn_call_${convId}`, "width=1000,height=720");
    if (!w) location.href = url;                                  // bị chặn popup -> mở ngay tab này
  };

  if (!SC.socket) return;
  let ring = null, tone = null;

  function playTone() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      let on = true;
      const beep = () => { if (!on) return; const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = 520; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination); o.start(); setTimeout(() => o.stop(), 700); };
      beep(); const t = setInterval(beep, 1800);
      return () => { on = false; clearInterval(t); ctx.close(); };
    } catch (e) { return () => {}; }
  }
  function close() { if (ring) { ring.remove(); ring = null; } if (tone) { tone(); tone = null; } }

  SC.socket.on("call:incoming", (p) => {
    close();
    const call = p.call, u = call.other;
    ring = el("div", "overlay ring-overlay"); ring.setAttribute("role", "alertdialog");
    const box = el("div", "dialog ring-box");
    const av = SC.avatar(u, "xl ring-avatar"); box.appendChild(av);
    const h = el("h3"); h.appendChild(document.createTextNode(SC.displayName(u))); h.appendChild(SC.badges(u)); box.appendChild(h);
    box.appendChild(el("p", "muted", call.video ? "📹 đang gọi video cho bạn…" : "📞 đang gọi thoại cho bạn…"));
    const a = el("div", "actions ring-actions");
    const no = el("button", "btn btn-danger", "✖ Từ chối"); no.onclick = () => { SC.socket.emit("call:decline", { call_id: call.id }); close(); };
    const yes = el("button", "btn btn-primary", call.video ? "🎥 Nghe" : "📞 Nghe");
    yes.onclick = () => { close(); const w = window.open(`/call/${call.id}`, `dn_call_in_${call.id}`, "width=1000,height=720"); if (!w) location.href = `/call/${call.id}`; };
    a.append(no, yes); box.appendChild(a);
    ring.appendChild(box); document.body.appendChild(ring);
    tone = playTone();
    ring.dataset.callId = call.id;
  });
  const maybeClose = (p) => { if (ring && parseInt(ring.dataset.callId, 10) === p.call_id) close(); };
  SC.socket.on("call:ended", maybeClose);
  SC.socket.on("call:accepted", maybeClose);
})();
