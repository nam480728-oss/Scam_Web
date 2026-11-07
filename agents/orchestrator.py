"""Dieu phoi Ve si theo SU KIEN TIN NHAN. Phan tich chay NEN (background task cua Socket.IO), khong lam cham chat.

Tin nhan moi -> tien xu ly van ban (agents/agent3_text.py) -> AI 3 (mo hinh da train, doc ca cuoc tro chuyen)
            -> bo quyet dinh luat 3 lan (agents/decision.py) -> lan 3: tu dong chan + bao 2 ben.
Tin AI 3 KHONG doc duoc (tin thoai, anh / tep khong kem chu): khong tinh lan, nhung neu nguoi gui da bi canh bao tu
lan 2 thi tin bi che (bam moi xem / nghe) va tep .apk bi chan tai.
"""
from __future__ import annotations

import logging
import time
import uuid

from agents import decision as dec
from agents.agent3_adapter import reader
from agents.agent3_text import analyze_text
from agents.contracts import PHASE_LABEL, SCENARIO_LABEL
from db.database import db, iso
from db.models import Conversation, Feedback, GuardianEvent, Message, Report, ScamCounter, User
from services.alert_manager import SELF_WARNING_TEXT
from services.realtime import emit_to, socketio

log = logging.getLogger("dangnam.orchestrator")
_app = None


def init(app):
    global _app
    _app = app


def room(model_key: str) -> str:
    return f"guardian:{model_key}"


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _stage(model_key: str, key: str, stage: str, status: str, summary: str | None = None, **extra):
    """Den bao tung buoc cho /demo va /guardian."""
    socketio.emit("guardian:stage", {"key": key, "stage": stage, "status": status, "summary": summary, **extra},
                  to=room(model_key))


def _run_bg(fn, *args):
    """Chay nen trong app context (test: chay dong bo de kiem tra duoc ket qua)."""
    if _app is None or not _app.config.get("GUARDIAN_ASYNC", True):
        return fn(*args)

    def task():
        with _app.app_context():
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - loi Ve si khong duoc lam sap chat
                log.exception("Loi xu ly nen %s", getattr(fn, "__name__", fn))
            finally:
                db.session.remove()
    socketio.start_background_task(task)


def conversation_window(conv: Conversation, receiver_id: int, upto_id: int) -> list[dict]:
    """Toi da 20 tin gan nhat (ca 2 phia) - AI 3 doc theo NGU CANH cuoc tro chuyen."""
    rows = (conv.messages.filter(Message.id <= upto_id, Message.kind != "call").order_by(Message.id.desc()).limit(20).all())
    out = []
    for m in reversed(rows):
        att = [m.attachment_name] if m.attachment_name else []
        out.append({"role": "receiver" if m.sender_id == receiver_id else "sender", "text": m.body or "",
                    "timestamp": iso(m.created_at), "attachments": att})
    return out


def _is_apk(msg: Message) -> bool:
    return bool(msg.attachment_name and msg.attachment_name.lower().endswith(".apk"))


# =========================================================================== #
# Tin nhan
# =========================================================================== #
def on_message(message_id: int):
    _run_bg(process_message, message_id)


def _push_message(msg: Message, conv: Conversation, receiver_id: int):
    from services import chat_service as cs
    emit_to(receiver_id, "guardian:message", {"message": cs.message_dto(msg, receiver_id),
                                              "conversation": cs.conversation_dto(conv, receiver_id)})


def process_message(message_id: int) -> GuardianEvent | None:
    msg = db.session.get(Message, message_id)
    if msg is None or msg.kind == "call":
        return None
    conv = db.session.get(Conversation, msg.conversation_id)
    receiver_id = conv.other_user_id(msg.sender_id)
    receiver, sender = db.session.get(User, receiver_id), db.session.get(User, msg.sender_id)
    if not receiver.agent3_enabled:                              # nguoi nhan tat AI 3: khong quet tin nhan
        msg.scan_status = "off"
        db.session.commit()
        _push_message(msg, conv, receiver_id)
        return None
    if not (msg.body or "").strip():
        return _unreadable(msg, conv, receiver, sender)

    from services.chat_service import are_friends
    key, mk = uuid.uuid4().hex[:10], receiver.model_key
    timings, t0 = {}, time.perf_counter()
    _stage(mk, key, "start", "running", kind="message", actor=sender.name, protected=receiver.name,
           text=(msg.body or msg.attachment_name or "")[:120])

    _stage(mk, key, "text", "running")
    text = analyze_text(msg.body)
    timings["text"] = _ms(t0)
    _stage(mk, key, "text", "done", f"{len(text['keywords'])} nhóm từ khóa" + (f" · {len(text['changes'])} chỗ lách chữ"
                                                                               if text["changes"] else ""))

    _stage(mk, key, "agent3", "running")
    payload = reader.build_payload(conversation_window(conv, receiver.id, msg.id), text, are_friends(sender.id, receiver.id))
    a3 = reader.analyze(payload)
    timings["agent3"] = a3.latency_ms
    _stage(mk, key, "agent3", "done", f"Rủi ro {a3.risk_score:.2f} · {SCENARIO_LABEL.get(a3.scenario, a3.scenario)}")

    t1 = time.perf_counter()
    counter = ScamCounter.query.filter_by(conversation_id=conv.id, user_id=sender.id).with_for_update().first()
    before = counter.flagged_count if counter else 0
    d = dec.decide(a3, text, _is_apk(msg), before)
    if d.flagged:
        if counter is None:
            counter = ScamCounter(conversation_id=conv.id, user_id=sender.id, flagged_count=0)
            db.session.add(counter)
        counter.flagged_count = before + 1
    timings["decision"] = _ms(t1)
    _stage(mk, key, "decision", "done", (f"Lần {d.counter_level}" + (" → CHẶN" if d.actions.get("block_sender") else ""))
           if d.flagged else "An toàn", level=d.level)

    msg.ai_checked, msg.ai_model = True, a3.model_name or a3.backend
    msg.ai_score, msg.ai_flagged = a3.model_prob if a3.model_prob is not None else a3.risk_score, d.flagged
    msg.warning_level, msg.scan_status = d.level, "done"
    timings["total"] = _ms(t0)
    ev = GuardianEvent(model_key=mk, kind="message", protected_id=receiver.id, actor_id=sender.id, message_id=msg.id,
                       level=d.level, agent3_called=True,
                       results={"text": text, "agent3": a3.to_dict(), "decision": d.to_dict()},
                       timings=timings, modes={"agent3": f"{a3.mode}:{a3.backend}" + (f"/{a3.model_name}" if a3.model_name else "")})
    db.session.add(ev)
    db.session.commit()

    if d.actions.get("block_sender"):                            # lan 3: tu dong chan TRUOC khi bao giao dien
        auto_block(receiver, sender, conv)
    _push_message(msg, conv, receiver.id)
    if d.level == 2:
        _notify_guardian(receiver, "tin nhắn lừa đảo lần 2", 2)
        from services.notify import notify
        notify(receiver.id, "scam_alert", f"🚨 Lần 2 {sender.name} gửi tin nghi lừa đảo "
                                         f"({SCENARIO_LABEL.get(a3.scenario, 'cảnh báo')}). Tin đã bị che; nếu thêm 1 lần nữa "
                                         f"Vệ sĩ sẽ tự động chặn.", link=f"/messages/{conv.id}", actor_id=sender.id, level=2)
    _broadcast(ev, key)
    return ev


def _unreadable(msg: Message, conv: Conversation, receiver: User, sender: User) -> GuardianEvent | None:
    """Tin thoai / anh / tep khong kem chu: AI 3 khong doc duoc -> KHONG tinh lan.
    Nguoi gui da bi canh bao tu lan 2 -> che tin (bam moi xem / nghe), chan tai .apk."""
    from services.alert_manager import get_count
    strikes = get_count(conv.id, sender.id)
    msg.scan_status = "done"
    ev = None
    if strikes >= 2:
        what = {"voice": "tin nhắn thoại", "image": "ảnh", "file": "tệp"}.get(msg.kind, "tin")
        msg.warning_level = 2
        if msg.kind == "voice":
            msg.attachment_meta = {**(msg.attachment_meta or {}), "masked": True}
        actions = {"mask": True, "block_apk": _is_apk(msg), "blur_links": False, "copy_delay": 0, "confirm_apk": False,
                   "block_sender": False, "family_hint": False}
        reason = (f"Vệ sĩ không đọc được nội dung {what}, nhưng {sender.name} đã gửi {strikes} tin lừa đảo trong cuộc chat "
                  f"này nên {what} bị che.")
        ev = GuardianEvent(model_key=receiver.model_key, kind="message", protected_id=receiver.id, actor_id=sender.id,
                           message_id=msg.id, level=2, agent3_called=False,
                           results={"unreadable": msg.kind, "decision": {"level": 2, "flagged": False, "counter_level": strikes,
                                                                         "reasons": [reason], "actions": actions}},
                           timings={}, modes={})
        db.session.add(ev)
    db.session.commit()
    _push_message(msg, conv, receiver.id)
    if ev is not None:
        _broadcast(ev)
    return ev


def auto_block(protected: User, offender: User, conv: Conversation) -> None:
    """Lan thu 3 phat hien lua dao: Ve si tu dong chan + bao CA 2 ben.
    Chi go duoc qua Khieu nai (2 ben chup anh truc tiep + Mat ma gia dinh + xac nhan nhau)."""
    from db.models import Appeal, Block
    from services import chat_service as cs
    from services.notify import notify
    # Vong lap: khieu nai thanh cong -> go chan, bo dem ve 0 -> neu lai lua dao 3 lan thi chan lai (lan chan thu N)
    nth = Appeal.query.filter_by(protected_id=protected.id, accused_id=offender.id, status="success").count() + 1
    again = f" (lần chặn thứ {nth})" if nth > 1 else ""
    row = Block.query.filter_by(blocker_id=protected.id, blocked_id=offender.id).first()
    if row is None:
        row = Block(blocker_id=protected.id, blocked_id=offender.id)
        db.session.add(row)
    row.source, row.reason = "guardian", f"Phát hiện tin nhắn lừa đảo lần thứ 3{again}"
    db.session.commit()
    cs._notify_block_change(protected.id, offender.id)
    notify(protected.id, "guardian_block", f"⛔ Vệ sĩ đã TỰ ĐỘNG CHẶN {offender.name} sau 3 lần gửi tin lừa đảo{again}. "
                                           f"Nếu đây là người thân bị chặn nhầm, hãy bấm Khiếu nại để xác minh và gỡ chặn. "
                                           f"Nếu bị lừa, bạn có thể gửi Yêu cầu thông tin truy vết tới quản trị viên.",
           link=f"/messages/{conv.id}", actor_id=offender.id, level=3)
    notify(offender.id, "guardian_block", f"⛔ {SELF_WARNING_TEXT}. Bạn đã bị chặn nhắn tin với {protected.name}{again}. "
                                          f"Nếu nhầm lẫn, hãy bấm Khiếu nại để xác minh danh tính.",
           link=f"/messages/{conv.id}", actor_id=None, level=3)
    _notify_guardian(protected, "kẻ gian bị tự động chặn sau 3 tin lừa đảo", 3)
    try:                                                         # truy vet IP (chi quan tri vien xem) - loi khong anh huong chan
        from services.trace_service import create_trace
        create_trace(protected, offender, conv, block_nth=nth)
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logging.getLogger("dangnam.trace").exception("Tao ho so truy vet that bai")


# =========================================================================== #
# Nguoi giam ho + bao cao / phan hoi (luu lam nhan train)
# =========================================================================== #
def _notify_guardian(protected: User, what: str, level: int):
    if protected and protected.guardian_id:
        from services.notify import notify
        notify(protected.guardian_id, "guardian", f"🛡️ {protected.name} vừa gặp cảnh báo lừa đảo ({what}). Hãy gọi hỏi thăm "
                                                  f"và nhắc người thân không chuyển tiền. Bạn không xem được nội dung tin nhắn.",
               link=f"/u/{protected.username}", actor_id=protected.id, level=level)


def _message_text(message_id: int | None) -> str | None:
    m = db.session.get(Message, message_id) if message_id else None
    return m.body if m else None


def report(reporter: User, reported_id: int, message_id: int | None = None, reason: str | None = None) -> dict:
    """Nguoi dung bam 'Bao cao lua dao': CHI luu lai (bao cao + nhan 'scam' kem noi dung tin) de lam du lieu train."""
    reported = db.session.get(User, reported_id)
    if reported is None or reported.id == reporter.id:
        return {"saved": False}
    db.session.add(Report(reporter_id=reporter.id, reported_id=reported_id, message_id=message_id, source="user",
                          reason=(reason or "")[:300] or None))
    db.session.add(Feedback(user_id=reporter.id, target_user_id=reported_id, message_id=message_id, label="scam",
                            text=_message_text(message_id)))
    db.session.commit()
    log.info("Bao cao %s -> %s (tin %s)", reporter.id, reported_id, message_id)
    return {"saved": True}


def feedback(user: User, label: str, message_id: int | None = None, target_user_id: int | None = None) -> None:
    db.session.add(Feedback(user_id=user.id, target_user_id=target_user_id, message_id=message_id, label=label,
                            text=_message_text(message_id)))
    db.session.commit()


# =========================================================================== #
# Hoi Ve si
# =========================================================================== #
def ask(user: User, text: str | None = None, conversation_id: int | None = None) -> dict:
    from services import chat_service as cs
    t0 = time.perf_counter()
    window, other, friend = None, None, False
    if conversation_id:
        conv = cs.get_conversation(conversation_id, user.id)
        other = conv.other_user_id(user.id)
        last = (conv.messages.filter(Message.sender_id == other, Message.kind != "call", Message.body.isnot(None))
                .order_by(Message.id.desc()).first())
        if last is None:
            return {"level": 0, "answer": "Người này chưa gửi tin nhắn nào cho bạn để kiểm tra.", "signals": []}
        window = conversation_window(conv, user.id, last.id)
        text = last.body
        friend = cs.are_friends(user.id, other)
    text = (text or "").strip()[:3000]
    if not text:
        return {"level": 0, "answer": "Hãy dán một đoạn tin nhắn để Vệ sĩ kiểm tra.", "signals": []}
    pre = analyze_text(text)
    window = window or [{"role": "sender", "text": text, "timestamp": None, "attachments": []}]
    a3 = reader.analyze(reader.build_payload(window, pre, friend))
    d = dec.decide(a3, pre, False, 0)
    ev = GuardianEvent(model_key=user.model_key, kind="ask", protected_id=user.id, actor_id=other, level=d.rule_level,
                       agent3_called=True, results={"text": pre, "agent3": a3.to_dict(), "decision": d.to_dict()},
                       timings={"agent3": a3.latency_ms, "total": _ms(t0)}, modes={"agent3": f"{a3.mode}:{a3.backend}"})
    db.session.add(ev)
    db.session.commit()
    _broadcast(ev)
    verdict = {0: "✅ Chưa thấy dấu hiệu lừa đảo.", 1: "⚠️ Có dấu hiệu cần thận trọng.",
               2: "🚨 Nhiều khả năng là lừa đảo.", 3: "⛔ Rất nguy hiểm – đây là lừa đảo."}[d.rule_level]
    advice = ["Không chuyển tiền, không đọc mã OTP cho bất kỳ ai.", "Gọi lại bằng số điện thoại quen thuộc để xác minh."]
    if pre.get("urls"):
        advice.append("Không bấm vào đường link trong tin nhắn.")
    if a3.scenario == "gia_nguoi_than":
        advice.append("Hỏi Mật mã gia đình để chắc chắn đó là người thân thật.")
    return {"level": d.rule_level, "verdict": verdict, "answer": a3.explanation_vi, "risk": a3.risk_score,
            "scenario": SCENARIO_LABEL.get(a3.scenario), "phase": PHASE_LABEL.get(a3.phase),
            "signals": a3.signals, "advice": advice if d.rule_level else [], "reasons": d.reasons}


# =========================================================================== #
# Phat su kien cho /guardian va /demo
# =========================================================================== #
def event_dto(e: GuardianEvent) -> dict:
    r = dict(e.results or {})
    if r.get("agent3"):
        r["agent3"] = {**r["agent3"], "scenario_label": SCENARIO_LABEL.get(r["agent3"].get("scenario")),
                       "phase_label": PHASE_LABEL.get(r["agent3"].get("phase"))}
    text = None
    if e.message_id:
        m = db.session.get(Message, e.message_id)
        if m is not None:
            text = m.body or ({"voice": "🎤 Tin nhắn thoại", "image": "📷 Ảnh"}.get(m.kind)
                              or (f"📎 {m.attachment_name}" if m.attachment_name else None))
    return {"id": e.id, "kind": e.kind, "level": e.level, "created_at": iso(e.created_at),
            "protected": e.protected.name if e.protected else None, "actor": e.actor.name if e.actor else None,
            "protected_id": e.protected_id, "actor_id": e.actor_id, "message_id": e.message_id,
            "text": text, "agent3_called": e.agent3_called, "results": r, "timings": e.timings or {}, "modes": e.modes or {}}


def _broadcast(ev: GuardianEvent, key: str | None = None):
    try:
        socketio.emit("guardian:event", {**event_dto(ev), "key": key}, to=room(ev.model_key))
    except Exception:  # noqa: BLE001
        log.exception("Khong phat duoc su kien Ve si")
