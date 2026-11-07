"""Cai dat: giao dien toi, bat/tat tung agent, xac minh (gia lap), Mat ma gia dinh, nguoi giam ho."""
import re

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from db.database import db
from db.models import FamilyMember, User
from routes import login_required_api, model_required
from services import chat_service as cs
from services import profile_service as ps
from services.notify import notify, user_brief

bp = Blueprint("settings", __name__)
ID_RE = re.compile(r"^\d{12}$")


def family_answer_key(answer: str) -> str:
    """Dap an duoc so khong phan biet hoa thuong / dau / khoang trang."""
    return re.sub(r"[^a-z0-9]", "", ps.fold(answer))


def _state(me: User) -> dict:
    friends = User.query.filter(User.id.in_(cs.friend_ids(me.id) or {0})).order_by(User.display_name).all()
    fam = {f.member_id: f.relation for f in FamilyMember.query.filter_by(user_id=me.id)}
    wards = User.query.filter_by(guardian_id=me.id).all()
    return {"dark_mode": me.dark_mode, "agents": {"agent3": me.agent3_enabled},
            "phone": me.phone, "phone_verified": me.phone_verified, "identity_verified": me.identity_verified,
            "family": {"question": me.family_question, "has_answer": bool(me.family_answer_hash),
                       "members": [{**user_brief(u), "relation": fam[u.id]} for u in friends if u.id in fam]},
            "guardian": user_brief(me.guardian) if me.guardian else None,
            "wards": [user_brief(u) for u in wards],
            "friends": [user_brief(u) for u in friends]}


@bp.get("/settings")
@model_required
@login_required
def settings_page():
    return render_template("settings.html", state=_state(current_user._get_current_object()), ok=request.args.get("ok"))


@bp.post("/api/settings")
@login_required_api
@model_required
def update_settings():
    me, data = current_user._get_current_object(), request.get_json(silent=True) or {}
    for key in ("dark_mode", "agent3_enabled"):
        if key in data:
            if not isinstance(data[key], bool):
                return jsonify(error="Giá trị không hợp lệ."), 400
            setattr(me, key, data[key])
    db.session.commit()
    return jsonify(_state(me))


@bp.post("/api/settings/verify-identity")
@login_required_api
@model_required
def verify_identity():
    """Gia lap eKYC: kiem tra dinh dang so CCCD 12 chu so. KHONG luu so CCCD, chi luu co da xac minh."""
    me, data = current_user._get_current_object(), request.get_json(silent=True) or {}
    if not ID_RE.match(str(data.get("id_number", "")).strip()):
        return jsonify(error="Số CCCD gồm 12 chữ số (giả lập, không lưu lại)."), 400
    if ps.fold(str(data.get("full_name", ""))) != ps.fold(me.display_name):
        return jsonify(error="Họ tên phải trùng với tên hiển thị trên hồ sơ."), 400
    me.identity_verified = True
    db.session.commit()
    return jsonify(_state(me))


@bp.post("/api/settings/family")
@login_required_api
@model_required
def update_family():
    me, data = current_user._get_current_object(), request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()
    answer = str(data.get("answer") or "").strip()
    members = data.get("members") or []
    if question and not (5 <= len(question) <= 200):
        return jsonify(error="Câu hỏi bí mật gồm 5–200 ký tự."), 400
    if not isinstance(members, list) or not all(isinstance(m, dict) for m in members):
        return jsonify(error="Danh sách người thân không hợp lệ."), 400
    friends = cs.friend_ids(me.id)
    me.family_question = question or None
    if answer:
        if len(family_answer_key(answer)) < 2:
            return jsonify(error="Đáp án quá ngắn."), 400
        me.family_answer_hash = generate_password_hash(family_answer_key(answer))
    elif not question:
        me.family_answer_hash = None
    FamilyMember.query.filter_by(user_id=me.id).delete()
    for m in members[:20]:
        uid = m.get("user_id")
        if isinstance(uid, int) and uid in friends:
            db.session.add(FamilyMember(user_id=me.id, member_id=uid, relation=str(m.get("relation") or "")[:40] or None))
    db.session.commit()
    return jsonify(_state(me))


@bp.post("/api/settings/guardian")
@login_required_api
@model_required
def update_guardian():
    me, data = current_user._get_current_object(), request.get_json(silent=True) or {}
    uid = data.get("user_id")
    if uid is None:
        me.guardian_id = None
        db.session.commit()
        return jsonify(_state(me))
    if not isinstance(uid, int) or uid not in cs.friend_ids(me.id):
        return jsonify(error="Người giám hộ phải là bạn bè của bạn."), 400
    changed = me.guardian_id != uid
    me.guardian_id = uid
    db.session.commit()
    if changed:
        notify(uid, "guardian", f"{me.name} đã chọn bạn làm người giám hộ. Bạn sẽ được báo khi {me.name} gặp cảnh báo lừa đảo "
                                f"nghiêm trọng (không xem được nội dung tin nhắn).", link=f"/u/{me.username}", actor_id=me.id)
    return jsonify(_state(me))
