/* Cửa sổ cuộc gọi: WebRTC 1-1 (signaling qua Socket.IO). Âm thanh / hình ảnh đi thẳng giữa 2 trình duyệt. */
(function () {
  "use strict";
  const SC = window.SC, page = document.getElementById("call-page");
  if (!SC || !page) return;
  const $ = (id) => document.getElementById(id);
  const { el } = SC;
  const socket = SC.socket;
  const other = JSON.parse($("call-data").textContent).other;
  const mode = page.dataset.mode, convId = parseInt(page.dataset.conv, 10), wantVideo = page.dataset.video === "1";
  const isCallee = mode === "incoming";
  let callId = parseInt(page.dataset.call, 10) || null;
  let pc = null, localStream = null, remoteStream = null, startedAt = null, timerT = null, ended = false;
  let pendingIce = [];

  const setStatus = (t) => { $("call-status").textContent = t; };
  const waitSocket = () => new Promise((res) => { if (socket.connected) res(); else socket.once("connect", res); });
  const emit = (ev, data, ms = 8000) => new Promise((res) => {
    let done = false; const t = setTimeout(() => { if (!done) { done = true; res({ error: "Máy chủ không phản hồi." }); } }, ms);
    socket.emit(ev, data, (r) => { if (!done) { done = true; clearTimeout(t); res(r || {}); } });
  });

  /* ------------------------------------------------------------ nguồn media */
  async function getMedia() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: wantVideo ? { width: { ideal: 640 }, height: { ideal: 480 } } : false }); }
    catch (e) {
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); SC.toast("Không mở được camera, chuyển sang chỉ âm thanh.", "warn"); }
      catch (e2) { stream = new MediaStream(); SC.toast("Không truy cập được micro / camera. Hãy cho phép trình duyệt dùng thiết bị.", "error"); }
    }
    return stream;
  }

  /* ------------------------------------------------------------ WebRTC */
  function createPeer() {
    pc = new RTCPeerConnection({ iceServers: (SC.cfg.ice || []) });
    localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));
    pc.ontrack = (e) => {
      remoteStream = e.streams[0];
      const rv = $("remote-video"); if (rv.srcObject !== remoteStream) rv.srcObject = remoteStream;
      if (remoteStream.getVideoTracks().length) page.classList.add("has-remote-video");
      startTimer();
    };
    pc.onicecandidate = (e) => { if (e.candidate) socket.emit("call:signal", { call_id: callId, data: { type: "ice", candidate: e.candidate } }); };
    pc.onconnectionstatechange = () => {
      const s = pc.connectionState;
      if (s === "connected") { setStatus("Đã kết nối"); startTimer(); }
      else if (s === "failed") setStatus("Kết nối thất bại (kiểm tra mạng / STUN).");
      else if (s === "disconnected") setStatus("Mất kết nối…");
    };
  }
  async function flushIce() { for (const c of pendingIce) { try { await pc.addIceCandidate(c); } catch (e) { /* bỏ qua */ } } pendingIce = []; }
  socket.on("call:signal", async (p) => {
    if (!callId || p.call_id !== callId || !pc) return;
    const d = p.data || {};
    try {
      if (d.type === "offer") {
        await pc.setRemoteDescription(d.sdp); await flushIce();
        const ans = await pc.createAnswer(); await pc.setLocalDescription(ans);
        socket.emit("call:signal", { call_id: callId, data: { type: "answer", sdp: pc.localDescription } });
      } else if (d.type === "answer") { await pc.setRemoteDescription(d.sdp); await flushIce(); }
      else if (d.type === "ice" && d.candidate) { if (pc.remoteDescription) await pc.addIceCandidate(d.candidate); else pendingIce.push(d.candidate); }
    } catch (e) { console.warn("Lỗi tín hiệu WebRTC", e); }
  });

  socket.on("call:accepted", async (p) => {
    if (p.call_id !== callId || isCallee) return;
    setStatus("Đang kết nối…");
    const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
    socket.emit("call:signal", { call_id: callId, data: { type: "offer", sdp: pc.localDescription } });
  });
  socket.on("call:ended", (p) => { if (p.call_id === callId) endUI(p.status, p.seconds); });

  function startTimer() {
    if (startedAt) return;
    startedAt = Date.now();
    timerT = setInterval(() => { const s = Math.floor((Date.now() - startedAt) / 1000); $("call-timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }, 1000);
  }
  function stopMedia() {
    if (pc) { try { pc.close(); } catch (e) { /* bỏ qua */ } }
    if (localStream) localStream.getTracks().forEach((t) => t.stop());
    clearInterval(timerT);
  }
  function endUI(status, secs) {
    if (ended) return; ended = true; stopMedia();
    const T = { declined: "Người nhận đã từ chối cuộc gọi", missed: "Không có người trả lời", ended: "Cuộc gọi đã kết thúc" };
    $("ended-title").textContent = T[status] || "Cuộc gọi đã kết thúc";
    $("ended-sub").textContent = secs ? `Thời lượng: ${Math.floor(secs / 60)} phút ${secs % 60} giây` : "";
    $("call-ended").classList.remove("hidden");
    setTimeout(() => { try { window.close(); } catch (e) { /* bỏ qua */ } }, 6000);
  }

  /* ------------------------------------------------------------ nút điều khiển */
  $("btn-mic").addEventListener("click", (e) => {
    const t = localStream && localStream.getAudioTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; e.currentTarget.classList.toggle("off", !t.enabled);
  });
  $("btn-cam").addEventListener("click", (e) => {
    const t = localStream && localStream.getVideoTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; e.currentTarget.classList.toggle("off", !t.enabled);
    $("local-video").classList.toggle("hidden", !t.enabled);
  });
  $("btn-end").addEventListener("click", async () => { if (callId && !ended) await emit("call:end", { call_id: callId }); endUI("ended"); });
  window.addEventListener("beforeunload", () => { if (callId && !ended) socket.emit("call:end", { call_id: callId }); });
  if (!wantVideo) $("btn-cam").classList.add("hidden");

  /* ------------------------------------------------------------ khởi động */
  async function startOutgoing() {
    setStatus("Đang mở micro / camera…");
    localStream = await getMedia();
    $("local-video").srcObject = localStream;
    createPeer();
    await waitSocket();
    const r = await emit("call:start", { conversation_id: convId, video: wantVideo });
    if (r.error) { setStatus(r.error); SC.toast(r.error, "error"); setTimeout(() => window.close(), 4000); ended = true; stopMedia(); return; }
    callId = r.call.id;
    setStatus(`Đang gọi ${other.name}…`);
  }
  async function startIncoming() {
    setStatus("Đang mở micro / camera…");
    localStream = await getMedia();
    $("local-video").srcObject = localStream;
    createPeer();
    await waitSocket();
    const r = await emit("call:accept", { call_id: callId });
    if (r.error) { setStatus(r.error); ended = true; stopMedia(); setTimeout(() => window.close(), 4000); return; }
    setStatus("Đang kết nối…");
  }
  if (isCallee) startIncoming(); else startOutgoing();

})();
