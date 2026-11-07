"""Trang quan tri (mat khau ADMIN_PASSWORD trong .env).

Tab:
  * Mo hinh AI  : thong tin mo hinh TF-IDF + SVM dang chay (chi so test, trang thai nap).
  * Truy vet    : ho so truy vet IP ke lua dao (tao khi Ve si tu dong chan - lan 3), loc + xuat CSV.
  * Yeu cau     : nan nhan xin xem thong tin truy vet -> Duyet / Tu choi.
  * Do uy tin   : diem so + chi tiet cong / tru cua nguoi gui loi moi ket ban (nguoi dung chi thay mau).
IP va diem uy tin CHI hien o day.
"""
import hmac
import time
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user

from db.database import db, iso
from db.models import FriendRequest, TraceRequest, User
from services import reputation_service as rs
from services import trace_service as ts
from services.ai_client import manager

bp = Blueprint("admin", __name__)
TABS = ("model", "traces", "requests", "reputation")


def is_admin() -> bool:
    return bool(session.get("is_admin"))


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if request.path.startswith("/api/"):
                return jsonify(error="Chỉ quản trị viên.", code="admin"), 403
            return redirect(url_for("admin.admin_page"))
        return view(*args, **kwargs)
    return wrapper


@bp.get("/")
def home():
    return redirect(url_for("feed.feed_page") if current_user.is_authenticated else url_for("auth.login"))


def _reputation_rows(limit: int = 60) -> list[dict]:
    rows = (FriendRequest.query.join(User, FriendRequest.sender_id == User.id).filter(User.model_key == manager.active)
            .order_by((FriendRequest.status == "pending").desc(), FriendRequest.id.desc()).limit(limit).all())
    out = []
    for r in rows:
        out.append({"id": r.id, "status": r.status, "created_at": iso(r.created_at), "sender": r.sender, "receiver": r.receiver,
                    "rep": rs.evaluate(r.sender, r.receiver_id)})
    return out


@bp.route("/admin", methods=["GET", "POST"])
def admin_page():
    error = None
    if request.method == "POST":
        ok = hmac.compare_digest((request.form.get("password") or "").encode(), current_app.config["ADMIN_PASSWORD"].encode())
        if ok:
            session["is_admin"] = True
            return redirect(url_for("admin.admin_page"))
        time.sleep(0.6)                                   # lam cham do mat khau
        error = "Sai mật khẩu quản trị."
    if not is_admin():
        return render_template("admin_login.html", error=error), (401 if error else 200)
    ts.purge_expired()
    tab = request.args.get("tab", "model")
    tab = tab if tab in TABS else "model"
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or "pending"
    ctx = {"tab": tab, "q": q, "status": status, "model": manager.info(),
           "pending_count": TraceRequest.query.filter_by(status="pending").count(),
           "retention_days": current_app.config["IP_RETENTION_DAYS"]}
    if tab == "traces":
        ctx["traces"] = ts.list_traces(q)
    elif tab == "requests":
        ctx["requests"] = ts.list_requests(None if status == "all" else status)
    elif tab == "reputation":
        ctx["rep_rows"] = _reputation_rows()
        ctx["rep_cfg"] = {k: current_app.config[k] for k in ("REPUTATION_BASE", "REPUTATION_GREEN", "REPUTATION_RED",
                                                             "REPUTATION_AGE_STEPS", "REPUTATION_MUTUAL_STEPS",
                                                             "REPUTATION_RENAME_STEPS")}
    return render_template("admin.html", **ctx)


@bp.post("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("auth.login"))


@bp.post("/admin/trace-requests/<int:rid>")
@admin_required
def resolve_trace_request(rid: int):
    action = request.form.get("action")
    if action not in ("approve", "reject"):
        abort(400)
    ts.resolve_request(rid, action == "approve", request.form.get("note"))
    return redirect(url_for("admin.admin_page", tab="requests"))


@bp.get("/admin/traces.csv")
@admin_required
def traces_csv():
    data = ts.export_csv(request.args.get("q"))
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=truy_vet_lua_dao.csv"})


# ---- JSON (quan tri) ----
@bp.get("/api/admin/traces")
@admin_required
def api_traces():
    return jsonify(traces=ts.list_traces(request.args.get("q")))


@bp.get("/api/admin/trace-requests")
@admin_required
def api_trace_requests():
    return jsonify(requests=ts.list_requests(request.args.get("status")))


@bp.post("/api/admin/trace-requests/<int:rid>")
@admin_required
def api_resolve_trace_request(rid: int):
    data = request.get_json(silent=True) or {}
    if data.get("action") not in ("approve", "reject"):
        return jsonify(error="Thao tác không hợp lệ."), 400
    r = ts.resolve_request(rid, data["action"] == "approve", data.get("note"))
    return jsonify(request=ts.request_dto(r, admin=True))


@bp.get("/api/admin/reputation/<int:uid>")
@admin_required
def api_reputation(uid: int):
    target = db.session.get(User, uid)
    if target is None or target.model_key != manager.active:
        return jsonify(error="Không tìm thấy."), 404
    return jsonify(reputation=rs.evaluate(target, request.args.get("viewer", type=int)))


@bp.get("/api/models/status")
def model_status():
    return jsonify(manager.status())
