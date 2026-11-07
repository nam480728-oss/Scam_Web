"""Ho so nguoi dung: ten hien thi (luu lich su), anh dai dien / anh bia (luu lich su + perceptual hash)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from flask import current_app
from unidecode import unidecode

from db.database import db, utcnow
from db.models import AvatarHistory, NameHistory, User

NAME_RE = re.compile(r"^[^\x00-\x1f<>]{2,80}$")
PHONE_RE = re.compile(r"^(0|\+84)(3|5|7|8|9)\d{8}$")


def fold(text: str) -> str:
    """Chu thuong, bo dau (dung cho tim kiem / so ten)."""
    return re.sub(r"\s+", " ", unidecode(text or "").lower()).strip()


def refresh_search_name(user: User):
    user.search_name = f"{fold(user.display_name)} {user.username.lower()}"[:200]


def clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def validate_name(name: str) -> str | None:
    if not NAME_RE.match(name):
        return "Họ tên gồm 2–80 ký tự."
    return None


def set_display_name(user: User, name: str, record: bool = True):
    name = clean_name(name)
    if user.display_name and user.display_name != name and record:
        db.session.add(NameHistory(user_id=user.id, old_name=user.display_name, new_name=name))
    user.display_name = name
    refresh_search_name(user)


def normalize_phone(raw: str) -> str | None:
    p = re.sub(r"[\s.\-()]", "", raw or "")
    return p if PHONE_RE.match(p) else None


# --------------------------------------------------------------------------- #
# Anh dai dien / anh bia
# --------------------------------------------------------------------------- #
def _save_image(file_storage, sub: str, max_side: int) -> str:
    """Kiem tra la anh that (Pillow mo duoc), thu nho, luu PNG/JPEG voi ten ngau nhien. Tra ve duong dan tuong doi."""
    from PIL import Image, UnidentifiedImageError

    cfg = current_app.config
    original = (file_storage.filename or "").lower()
    ext = original.rsplit(".", 1)[-1] if "." in original else ""
    if ext not in cfg["IMAGE_EXTS"]:
        raise ValueError("Chỉ nhận ảnh png, jpg, gif, webp.")
    data = file_storage.read()
    if not data:
        raise ValueError("Tệp rỗng.")
    if len(data) > cfg["MAX_UPLOAD_BYTES"]:
        raise ValueError(f"Ảnh quá lớn (tối đa {cfg['MAX_UPLOAD_BYTES'] // 2**20} MB).")
    import io
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError):
        raise ValueError("Tệp không phải ảnh hợp lệ.")
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    folder = Path(cfg["PUBLIC_UPLOAD_DIR"]) / sub
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    im.save(folder / name, "JPEG", quality=88)
    return f"{sub}/{name}"


def set_avatar_from_path(user: User, rel_path: str, record: bool = True):
    if record:
        db.session.add(AvatarHistory(user_id=user.id, path=rel_path, changed_at=utcnow()))
    user.avatar_path = rel_path


def upload_avatar(user: User, file_storage):
    set_avatar_from_path(user, _save_image(file_storage, "avatars", 512))


def upload_cover(user: User, file_storage):
    user.cover_path = _save_image(file_storage, "covers", 1400)


def save_post_image(file_storage) -> str:
    return _save_image(file_storage, "posts", 1400)


def avatar_url(user: User) -> str | None:
    return f"/static/uploads/{user.avatar_path}" if user.avatar_path else None
