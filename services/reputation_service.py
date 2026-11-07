"""Do uy tin cua tai khoan (nguoi gui loi moi ket ban / nguoi la nhan tin) - luat RIENG, khong lien quan AI 3 / luat 3 lan.

Diem goc REPUTATION_BASE (70), cong / tru theo 3 tieu chi roi kep trong 0..100:
  * Tuoi tai khoan     : moi tao -> tru, lau nam -> cong
  * Ban chung voi nguoi xem : nhieu -> cong, khong co -> tru   (vi vay diem tinh theo CAP nguoi xem - nguoi bi xem)
  * So lan doi ten     : doi nhieu -> tru, chua doi -> cong
Mau: xanh >= REPUTATION_GREEN (80) · vang · do < REPUTATION_RED (50).

Nguoi dung CHI thay mau + nhan (badge). Diem so + chi tiet cong / tru CHI quan tri vien thay (evaluate).
"""
from __future__ import annotations

from flask import current_app

from db.database import utcnow
from db.models import NameHistory, User
from services.chat_service import friend_ids

LEVELS = {
    "green": {"label": "Đáng tin", "hint": "Tài khoản lâu năm, có bạn chung, ít đổi tên."},
    "yellow": {"label": "Cân nhắc", "hint": "Chưa đủ thông tin để tin tưởng. Hãy thận trọng khi được nhờ chuyển tiền."},
    "red": {"label": "Cảnh giác", "hint": "Tài khoản có dấu hiệu đáng ngờ (mới tạo, ít bạn chung hoặc đổi tên nhiều lần)."},
}


def _step(value: float, steps, strict: bool = False) -> int:
    """steps = [(nguong, diem), ..., (None, diem)] -> diem cua bac dau tien ma value <= nguong (strict: value < nguong)."""
    for limit, points in steps:
        if limit is None or (value < limit if strict else value <= limit):
            return points
    return steps[-1][1]


def _age_text(days: int) -> str:
    if days < 1:
        return "dưới 1 ngày"
    if days < 60:
        return f"{days} ngày"
    if days < 730:
        return f"{days // 30} tháng"
    return f"{days // 365} năm"


def level_of(score: int) -> str:
    cfg = current_app.config
    if score >= cfg["REPUTATION_GREEN"]:
        return "green"
    if score < cfg["REPUTATION_RED"]:
        return "red"
    return "yellow"


def evaluate(target: User, viewer_id: int | None) -> dict:
    """Day du (CHI quan tri vien): {score, level, label, items: [{key, text, value, points}]}."""
    cfg = current_app.config
    age = max((utcnow() - target.created_at).total_seconds(), 0) / 86400 if target.created_at else 0.0
    mutual = len(friend_ids(target.id) & friend_ids(viewer_id)) if viewer_id and viewer_id != target.id else 0
    renames = NameHistory.query.filter_by(user_id=target.id).count()
    items = [
        {"key": "age", "value": int(age), "text": f"Tài khoản tạo được {_age_text(int(age))}",
         "points": _step(age, cfg["REPUTATION_AGE_STEPS"], strict=True)},
        {"key": "mutual", "value": mutual, "text": f"{mutual} bạn chung" if mutual else "Không có bạn chung",
         "points": _step(mutual, cfg["REPUTATION_MUTUAL_STEPS"])},
        {"key": "renames", "value": renames, "text": f"Đổi tên {renames} lần" if renames else "Chưa từng đổi tên",
         "points": _step(renames, cfg["REPUTATION_RENAME_STEPS"])},
    ]
    score = max(0, min(100, cfg["REPUTATION_BASE"] + sum(i["points"] for i in items)))
    level = level_of(score)
    return {"score": score, "base": cfg["REPUTATION_BASE"], "level": level, "label": LEVELS[level]["label"], "items": items}


def badge(target: User, viewer_id: int | None) -> dict:
    """Cho nguoi dung: CHI mau + nhan + goi y (khong co diem so, khong co chi tiet)."""
    level = evaluate(target, viewer_id)["level"]
    return {"level": level, "label": LEVELS[level]["label"], "hint": LEVELS[level]["hint"]}
