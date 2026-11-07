"""Khieu nai go chan (sau khi Ve si tu dong chan): trang /appeal/<id> + API chup xac minh / tra loi / xac nhan."""
from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from routes import login_required_api, model_required
from services import appeal_service as aps

bp = Blueprint("appeal", __name__)


def _me():
    return current_user._get_current_object()


@bp.get("/appeal/<int:aid>")
@model_required
@login_required
def appeal_page(aid: int):
    a = aps.get_appeal(aid, current_user.id)
    return render_template("appeal.html", appeal_id=a.id)


@bp.post("/api/appeals")
@login_required_api
@model_required
def open_appeal():
    uid = (request.get_json(silent=True) or {}).get("user_id")
    if not isinstance(uid, int) or isinstance(uid, bool):
        return jsonify(error="Thiếu người cần khiếu nại."), 400
    a = aps.open_appeal(_me(), uid)
    return jsonify(appeal=aps.view(a, current_user.id)), 201


@bp.get("/api/appeals/<int:aid>")
@login_required_api
@model_required
def get_appeal(aid: int):
    return jsonify(appeal=aps.view(aps.get_appeal(aid, current_user.id), current_user.id))


@bp.post("/api/appeals/<int:aid>/challenge")
@login_required_api
@model_required
def challenge(aid: int):
    return jsonify(aps.new_challenge(aps.get_appeal(aid, current_user.id), _me()))


@bp.post("/api/appeals/<int:aid>/capture")
@login_required_api
@model_required
def capture(aid: int):
    files = [request.files.get(f"frame{i}") for i in range(3)]
    if any(f is None for f in files):
        return jsonify(error="Cần đủ 3 khung hình."), 400
    a = aps.get_appeal(aid, current_user.id)
    return jsonify(aps.submit_capture(a, _me(), request.form.get("nonce", ""), files))


@bp.post("/api/appeals/<int:aid>/answer")
@login_required_api
@model_required
def answer(aid: int):
    ans = (request.get_json(silent=True) or {}).get("answer")
    if not isinstance(ans, str):
        return jsonify(error="Thiếu câu trả lời."), 400
    a = aps.get_appeal(aid, current_user.id)
    return jsonify({**aps.answer_question(a, _me(), ans), "appeal": aps.view(a, current_user.id)})


@bp.post("/api/appeals/<int:aid>/confirm")
@login_required_api
@model_required
def confirm(aid: int):
    accept = (request.get_json(silent=True) or {}).get("accept")
    if not isinstance(accept, bool):
        return jsonify(error="Thiếu lựa chọn xác nhận."), 400
    return jsonify(appeal=aps.confirm(aps.get_appeal(aid, current_user.id), _me(), accept))


@bp.get("/api/appeals/<int:aid>/photo/<int:cid>/<int:idx>")
@login_required_api
def photo(aid: int, cid: int, idx: int):
    a = aps.get_appeal(aid, current_user.id)
    path = aps.photo_path(a, cid, idx, current_user.id)
    if not path.is_file():
        return jsonify(error="Ảnh không còn."), 404
    resp = send_file(path, mimetype="image/jpeg", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp
