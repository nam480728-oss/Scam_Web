"""Dang ky / dang nhap / dang xuat / xac minh so dien thoai bang OTP gia lap."""
import re
import secrets
import time
from urllib.parse import urlparse

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from db.database import db
from db.models import AVATAR_COLORS, User
from routes import model_required
from services import profile_service as ps
from services.ai_client import manager

bp = Blueprint("auth", __name__)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
OTP_TTL = 300


def _safe_next(target: str | None) -> str:
    if target:
        p = urlparse(target)
        if not p.netloc and not p.scheme and target.startswith("/") and not target.startswith("//"):
            return target
    return url_for("feed.feed_page")


@bp.route("/login", methods=["GET", "POST"])
@model_required
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_page"))
    error, username = None, ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = (User.query.filter(User.model_key == manager.active, func.lower(User.username) == username.lower()).first()
                if username else None)
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(_safe_next(request.args.get("next")))
        error = "Tên tài khoản hoặc mật khẩu không đúng."
    demo = []
    if current_app.config.get("DEMO_QUICK_LOGIN"):
        from services.demo_service import demo_accounts
        demo = demo_accounts(manager.active)
    return render_template("login.html", error=error, username=username, demo=demo)


@bp.route("/register", methods=["GET", "POST"])
@model_required
def register():
    if current_user.is_authenticated:
        return redirect(url_for("feed.feed_page"))
    error, form = None, {"username": "", "display_name": "", "phone": ""}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        username, display_name = form["username"], ps.clean_name(form["display_name"])
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        phone = ps.normalize_phone(form["phone"]) if form["phone"] else None
        if ps.validate_name(display_name):
            error = ps.validate_name(display_name)
        elif not USERNAME_RE.match(username):
            error = "Tên tài khoản gồm 3–30 ký tự: chữ cái không dấu, số, dấu chấm hoặc gạch dưới."
        elif form["phone"] and not phone:
            error = "Số điện thoại không hợp lệ (ví dụ 0912345678)."
        elif len(password) < 6:
            error = "Mật khẩu phải có ít nhất 6 ký tự."
        elif len(password) > 128:
            error = "Mật khẩu quá dài."
        elif password != confirm:
            error = "Hai lần nhập mật khẩu không khớp."
        elif User.query.filter(User.model_key == manager.active, func.lower(User.username) == username.lower()).first():
            error = "Tên tài khoản đã tồn tại."
        if not error:
            user = User(username=username, model_key=manager.active, phone=phone,
                        avatar_color=AVATAR_COLORS[User.query.filter_by(model_key=manager.active).count() % len(AVATAR_COLORS)])
            ps.set_display_name(user, display_name, record=False)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except Exception:                                     # dang ky dong thoi cung ten
                db.session.rollback()
                error = "Tên tài khoản đã tồn tại."
            else:
                login_user(user, remember=True)
                return redirect(url_for("auth.verify_phone") if phone else url_for("feed.feed_page"))
    return render_template("register.html", error=error, form=form)


# --------------------------------------------------------------------------- #
# OTP gia lap: ma hien ngay tren man hinh (khong gui SMS that)
# --------------------------------------------------------------------------- #
def _new_otp(phone: str) -> str:
    code = f"{secrets.randbelow(10**6):06d}"
    session["otp"] = {"phone": phone, "code": code, "exp": time.time() + OTP_TTL, "tries": 0}
    return code


@bp.route("/verify-phone", methods=["GET", "POST"])
@model_required
@login_required
def verify_phone():
    me = current_user
    error, info = None, None
    otp = session.get("otp")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "send":
            phone = ps.normalize_phone(request.form.get("phone") or "")
            if not phone:
                error = "Số điện thoại không hợp lệ (ví dụ 0912345678)."
            else:
                me.phone, me.phone_verified = phone, False
                db.session.commit()
                _new_otp(phone)
                info = "Đã gửi mã OTP (giả lập)."
        elif action == "verify":
            code = (request.form.get("code") or "").strip()
            if not otp or otp.get("phone") != me.phone or time.time() > otp.get("exp", 0):
                error = "Mã OTP đã hết hạn, hãy gửi lại."
            elif otp.get("tries", 0) >= 5:
                error = "Nhập sai quá nhiều lần, hãy gửi lại mã mới."
            elif not secrets.compare_digest(code, otp["code"]):
                otp["tries"] = otp.get("tries", 0) + 1
                session["otp"] = otp
                error = "Mã OTP không đúng."
            else:
                me.phone_verified = True
                db.session.commit()
                session.pop("otp", None)
                return redirect(url_for("settings.settings_page", ok="phone"))
    elif me.phone and not me.phone_verified and (not otp or otp.get("phone") != me.phone or time.time() > otp["exp"]):
        _new_otp(me.phone)                                       # vua dang ky co SDT: gui ma ngay
    otp = session.get("otp")
    show = otp if otp and otp.get("phone") == me.phone and time.time() <= otp["exp"] else None
    return render_template("verify_phone.html", error=error, info=info, otp=show)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
