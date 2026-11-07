"""Du lieu canh bao hien thi tren tin nhan - CHI cho NGUOI NHAN (nguoi duoc bao ve).

Lay tu GuardianEvent cua tin: giai thich (explanation_vi cua AI 3), dau hieu, kich ban / pha, goi y Mat ma gia dinh,
link trong tin (lam mo), STK (dem nguoc khi copy), che tin / chan tai APK, phan hoi da gui.
"""
from __future__ import annotations

from agents.contracts import PHASE_LABEL, SCENARIO_LABEL
from db.database import db
from db.models import Feedback, GuardianEvent, User


def message_guards(message_ids: list[int], viewer_id: int) -> dict[int, dict]:
    ids = [i for i in message_ids if i]
    if not ids:
        return {}
    events = GuardianEvent.query.filter(GuardianEvent.message_id.in_(ids), GuardianEvent.kind == "message",
                                        GuardianEvent.protected_id == viewer_id).all()
    fb = {f.message_id: f.label for f in Feedback.query.filter(Feedback.message_id.in_(ids), Feedback.user_id == viewer_id)}
    viewer = db.session.get(User, viewer_id)
    out = {}
    for e in events:
        r = e.results or {}
        a3, tx, d = r.get("agent3") or {}, r.get("text") or {}, r.get("decision") or {}
        actions = d.get("actions") or {}
        explanation = a3.get("explanation_vi") or (d.get("reasons") or [None])[0]
        out[e.message_id] = {
            "event_id": e.id, "level": e.level, "risk": a3.get("risk_score"), "explanation": explanation,
            "signals": list(dict.fromkeys(a3.get("signals") or []))[:8], "scenario": a3.get("scenario"),
            "scenario_label": SCENARIO_LABEL.get(a3.get("scenario")), "phase": a3.get("phase"),
            "phase_label": PHASE_LABEL.get(a3.get("phase")), "unreadable": r.get("unreadable"),
            "family_hint": bool(actions.get("family_hint")),
            "family_question": viewer.family_question if viewer and actions.get("family_hint") else None,
            "urls": [{"url": u["url"], "domain": u["domain"]} for u in tx.get("urls", [])],
            "accounts": tx.get("bank_accounts", []),
            "blur_links": bool(actions.get("blur_links")), "copy_delay": actions.get("copy_delay", 0),
            "mask": bool(actions.get("mask")), "block_apk": bool(actions.get("block_apk")),
            "reasons": d.get("reasons", []), "feedback": fb.get(e.message_id), "changes": tx.get("changes", []),
        }
    return out


def message_detail(message_id: int, viewer_id: int) -> dict | None:
    """Chi tiet cho nut "Vi sao?" (chi nguoi nhan)."""
    e = GuardianEvent.query.filter_by(message_id=message_id, kind="message", protected_id=viewer_id).first()
    if e is None:
        return None
    from agents.orchestrator import event_dto
    return event_dto(e)
