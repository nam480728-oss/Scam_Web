"""Nan nhan gui yeu cau xem thong tin truy vet (IP, vi tri gan dung) cua ke da bi Ve si tu dong chan.
Quan tri vien duyet o /admin -> nan nhan xem duoc phan cua vu lien quan toi minh."""
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from routes import login_required_api
from services import trace_service as ts

bp = Blueprint("trace", __name__)


@bp.get("/trace-requests")
@login_required
def trace_requests_page():
    return render_template("trace_requests.html", requests=ts.my_requests(current_user))


@bp.get("/api/trace-requests")
@login_required_api
def my_trace_requests():
    return jsonify(requests=ts.my_requests(current_user))


@bp.post("/api/trace-requests")
@login_required_api
def create_trace_request():
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    if not isinstance(uid, int) or isinstance(uid, bool):
        return jsonify(error="Người dùng không hợp lệ."), 400
    reason = data.get("reason")
    if reason is not None and not isinstance(reason, str):
        return jsonify(error="Lý do không hợp lệ."), 400
    r = ts.create_request(current_user, uid, reason or "")
    return jsonify(request=ts.request_dto(r)), 201
