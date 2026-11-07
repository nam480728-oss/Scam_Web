"""Truy vet IP ke lua dao.

* Moi tin nhan luu IP + trinh duyet nguoi gui (chat_service.send_message); moi lan dang nhap ghi login_logs
  (tin hieu user_logged_in). Hai loai nay tu xoa sau IP_RETENTION_DAYS.
* Ve si TU DONG CHAN (lan 3) -> create_trace(): ho so truy vet giu lau dai (IP cac tin bi gan co + IP dang nhap gan nhat,
  vi tri gan dung).
* CHI quan tri vien xem toan bo. Nan nhan gui yeu cau -> quan tri vien duyet -> nan nhan xem phan cua vu lien quan toi minh.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import timedelta

from flask import current_app, has_request_context, request
from flask_login import user_logged_in

from db.database import db, iso, utcnow
from db.models import Conversation, LoginLog, Message, ScamTrace, TraceRequest, User
from services import ip_geo
from services.chat_service import ChatError

log = logging.getLogger("dangnam.trace")
REASON_MIN, REASON_MAX, NOTE_MAX = 10, 500, 500
PURGE_EVERY = 3600.0
_last_purge = 0.0


# --------------------------------------------------------------------------- #
# Ghi IP
# --------------------------------------------------------------------------- #
def request_meta() -> tuple[str | None, str | None]:
    """(ip, user_agent) cua request hien tai - None neu khong co request (vd tin gui tu kich ban demo)."""
    if not has_request_context():
        return None, None
    return ip_geo.client_ip(request), ip_geo.user_agent(request)


def _on_login(sender, user, **extra):
    try:
        ip, ua = request_meta()
        db.session.add(LoginLog(user_id=user.id, ip=ip, user_agent=ua))
        db.session.commit()
        purge_expired()
    except Exception:  # noqa: BLE001 - ghi log dang nhap loi khong duoc chan dang nhap
        db.session.rollback()
        log.exception("Khong ghi duoc login_logs")


def init(app):
    user_logged_in.connect(_on_login, app)


def purge_expired(force: bool = False) -> int:
    """Xoa IP tin nhan + nhat ky dang nhap cu hon IP_RETENTION_DAYS (toi da 1 lan / gio). Ho so truy vet KHONG bi xoa."""
    global _last_purge
    if not force and time.time() - _last_purge < PURGE_EVERY:
        return 0
    _last_purge = time.time()
    cutoff = utcnow() - timedelta(days=current_app.config["IP_RETENTION_DAYS"])
    n = (Message.query.filter(Message.created_at < cutoff, Message.sender_ip.isnot(None))
         .update({Message.sender_ip: None, Message.sender_user_agent: None}, synchronize_session=False))
    n += LoginLog.query.filter(LoginLog.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    return n


# --------------------------------------------------------------------------- #
# Tao ho so truy vet (lan 3 - tu dong chan)
# --------------------------------------------------------------------------- #
def create_trace(protected: User, offender: User, conv: Conversation, block_nth: int = 1) -> ScamTrace:
    flagged = (Message.query.filter_by(conversation_id=conv.id, sender_id=offender.id, ai_flagged=True)
               .order_by(Message.id.desc()).limit(10).all())
    logins = LoginLog.query.filter_by(user_id=offender.id).order_by(LoginLog.id.desc()).limit(5).all()
    geo_cache: dict[str, dict] = {}

    def geo(ip):
        if ip not in geo_cache:
            geo_cache[ip] = ip_geo.geolocate(ip)
        return geo_cache[ip]

    msgs = [{"message_id": m.id, "at": iso(m.created_at), "ip": m.sender_ip, "user_agent": m.sender_user_agent,
             "level": m.warning_level, "text": (m.body or m.attachment_name or "")[:200]} for m in flagged]
    login_rows = [{"at": iso(r.created_at), "ip": r.ip, "user_agent": r.user_agent} for r in logins]
    primary = next((m for m in flagged if m.sender_ip), None)
    ip = primary.sender_ip if primary else next((r.ip for r in logins if r.ip), None)
    ua = primary.sender_user_agent if primary else next((r.user_agent for r in logins if r.ip), None)
    ips = []
    for item_ip in [m["ip"] for m in msgs] + [r["ip"] for r in login_rows]:
        if item_ip and item_ip not in [x["ip"] for x in ips]:
            g = geo(item_ip)
            ips.append({"ip": item_ip, "place": ip_geo.place(g), "isp": g.get("isp"), "source": g["source"]})
    g = geo(ip) if ip else ip_geo.geolocate(None)
    trace = ScamTrace(model_key=protected.model_key, offender_id=offender.id, victim_id=protected.id, conversation_id=conv.id,
                      offender_username=offender.username, offender_name=offender.name,
                      victim_username=protected.username, victim_name=protected.name, block_nth=block_nth,
                      ip=ip, user_agent=ua, country=g.get("country"), region=g.get("region"), city=g.get("city"),
                      isp=g.get("isp"), geo_source=g["source"],
                      evidence={"messages": msgs, "logins": login_rows, "ips": ips})
    db.session.add(trace)
    db.session.commit()
    log.info("Tao ho so truy vet #%s: %s -> %s ip=%s (%s)", trace.id, offender.username, protected.username, ip, g["source"])
    return trace


# --------------------------------------------------------------------------- #
# Hien thi
# --------------------------------------------------------------------------- #
def _geo_of(t: ScamTrace) -> dict:
    return {"country": t.country, "region": t.region, "city": t.city}


def trace_dto(t: ScamTrace) -> dict:
    """Day du - CHI cho quan tri vien."""
    return {"id": t.id, "created_at": iso(t.created_at), "block_nth": t.block_nth,
            "offender": {"id": t.offender_id, "username": t.offender_username, "name": t.offender_name},
            "victim": {"id": t.victim_id, "username": t.victim_username, "name": t.victim_name},
            "conversation_id": t.conversation_id, "ip": t.ip, "user_agent": t.user_agent, "place": ip_geo.place(_geo_of(t)),
            "isp": t.isp, "geo_source": t.geo_source, "geo_label": ip_geo.SOURCE_LABEL.get(t.geo_source, t.geo_source),
            "evidence": t.evidence or {}}


def victim_view(t: ScamTrace) -> dict:
    """Phan nan nhan duoc xem khi yeu cau duoc duyet: IP + vi tri gan dung + thoi gian (khong co trinh duyet, ghi chu noi bo)."""
    ev = t.evidence or {}
    return {"id": t.id, "created_at": iso(t.created_at), "offender_name": t.offender_name, "offender_username": t.offender_username,
            "ip": t.ip, "place": ip_geo.place(_geo_of(t)), "isp": t.isp,
            "geo_label": ip_geo.SOURCE_LABEL.get(t.geo_source, t.geo_source),
            "messages": [{"at": m.get("at"), "ip": m.get("ip")} for m in ev.get("messages", [])],
            "ips": ev.get("ips", [])}


def request_dto(r: TraceRequest, admin: bool = False) -> dict:
    d = {"id": r.id, "status": r.status, "reason": r.reason, "admin_note": r.admin_note, "created_at": iso(r.created_at),
         "resolved_at": iso(r.resolved_at), "trace_id": r.trace_id,
         "offender_name": r.trace.offender_name, "offender_username": r.trace.offender_username}
    if admin:
        d["requester"] = {"id": r.requester_id, "username": r.requester.username, "name": r.requester.name}
        d["trace"] = trace_dto(r.trace)
    elif r.status == "approved":
        d["trace"] = victim_view(r.trace)
    return d


# --------------------------------------------------------------------------- #
# Nan nhan gui yeu cau
# --------------------------------------------------------------------------- #
def latest_trace_for(victim_id: int, offender_id: int) -> ScamTrace | None:
    return (ScamTrace.query.filter_by(victim_id=victim_id, offender_id=offender_id)
            .order_by(ScamTrace.id.desc()).first())


def request_state(victim_id: int, offender_id: int) -> dict | None:
    """Trang thai cho nut 'Yeu cau thong tin truy vet' (None = khong co ho so -> an nut)."""
    t = latest_trace_for(victim_id, offender_id)
    if t is None:
        return None
    r = (TraceRequest.query.filter_by(trace_id=t.id, requester_id=victim_id)
         .order_by(TraceRequest.id.desc()).first())
    return {"trace_id": t.id, "request_id": r.id if r else None, "status": r.status if r else None}


def create_request(me: User, offender_id: int, reason: str) -> TraceRequest:
    reason = (reason or "").strip()
    if not REASON_MIN <= len(reason) <= REASON_MAX:
        raise ChatError(f"Hãy ghi lý do từ {REASON_MIN} đến {REASON_MAX} ký tự.")
    t = latest_trace_for(me.id, offender_id)
    if t is None:                                          # chi nan nhan cua 1 vu tu dong chan moi gui duoc
        raise ChatError("Không có hồ sơ truy vết nào liên quan tới bạn và người này.", 404)
    existing = (TraceRequest.query.filter(TraceRequest.trace_id == t.id, TraceRequest.requester_id == me.id,
                                          TraceRequest.status.in_(("pending", "approved"))).first())
    if existing:
        raise ChatError("Bạn đã gửi yêu cầu cho vụ này rồi." if existing.status == "pending"
                        else "Yêu cầu của bạn đã được duyệt, xem ở trang Yêu cầu truy vết.", 409)
    r = TraceRequest(trace_id=t.id, requester_id=me.id, reason=reason)
    db.session.add(r)
    db.session.commit()
    return r


def my_requests(me: User) -> list[dict]:
    rows = TraceRequest.query.filter_by(requester_id=me.id).order_by(TraceRequest.id.desc()).all()
    return [request_dto(r) for r in rows]


# --------------------------------------------------------------------------- #
# Quan tri vien
# --------------------------------------------------------------------------- #
def list_traces(q: str | None = None, limit: int = 200) -> list[dict]:
    query = ScamTrace.query
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(ScamTrace.offender_username.like(like) | ScamTrace.offender_name.like(like) |
                             ScamTrace.victim_username.like(like) | ScamTrace.ip.like(like))
    return [trace_dto(t) for t in query.order_by(ScamTrace.id.desc()).limit(limit).all()]


def list_requests(status: str | None = None) -> list[dict]:
    query = TraceRequest.query
    if status in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status)
    return [request_dto(r, admin=True) for r in query.order_by(TraceRequest.id.desc()).limit(200).all()]


def resolve_request(rid: int, approve: bool, note: str | None) -> TraceRequest:
    r = db.session.get(TraceRequest, rid)
    if r is None:
        raise ChatError("Không tìm thấy yêu cầu.", 404)
    if r.status != "pending":
        raise ChatError("Yêu cầu này đã được xử lý.", 409)
    note = (note or "").strip()[:NOTE_MAX] or None
    r.status, r.admin_note, r.resolved_at = ("approved" if approve else "rejected"), note, utcnow()
    db.session.commit()
    from services.notify import notify
    if approve:
        text = f"✅ Quản trị viên đã DUYỆT yêu cầu truy vết về {r.trace.offender_name}. Bấm để xem thông tin."
    else:
        text = f"❌ Quản trị viên đã từ chối yêu cầu truy vết về {r.trace.offender_name}" + (f": {note}" if note else ".")
    notify(r.requester_id, "trace", text, link="/trace-requests", level=1)
    return r


CSV_FIELDS = ["id", "thoi_gian", "lan_chan", "ke_gui", "ten_ke_gui", "nan_nhan", "ip", "vi_tri", "nha_mang", "nguon_dinh_vi",
              "trinh_duyet", "cac_ip_khac"]


def export_csv(q: str | None = None) -> str:
    buf = io.StringIO()
    buf.write("﻿")                                    # BOM: Excel doc dung tieng Viet
    w = csv.writer(buf)
    w.writerow(CSV_FIELDS)
    for t in list_traces(q, limit=10000):
        others = "; ".join(f"{x['ip']} ({x['place']})" for x in t["evidence"].get("ips", []) if x["ip"] != t["ip"])
        w.writerow([t["id"], t["created_at"], t["block_nth"], t["offender"]["username"], t["offender"]["name"],
                    t["victim"]["username"], t["ip"] or "", t["place"], t["isp"] or "", t["geo_label"], t["user_agent"] or "",
                    others])
    return buf.getvalue()
