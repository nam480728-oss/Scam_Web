"""Cac blueprint cua ung dung."""
from functools import wraps

from flask import jsonify, request
from flask_login import current_user


def wants_json() -> bool:
    return request.path.startswith("/api/")


def login_required_api(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error="Bạn cần đăng nhập.", code="auth"), 401
        return view(*args, **kwargs)
    return wrapper
