"""Khieu nai go chan: khi Ve si TU DONG chan (lan 3 phat hien lua dao) ma co the la nham (vd con nhan me nho chuyen tien gap).

Ca 2 ben (nguoi duoc bao ve va nguoi bi chan) deu mo duoc khieu nai. Go chan chi khi DU ca:
    1. Ca 2 ben chup truc tiep (webcam, khong tai anh co san): lam theo 1 thao tac ngau nhien, tu chup 3 khung ~3 giay.
       May chu kiem tra: co mat trong it nhat 2/3 khung (OpenCV), cac khung co chuyen dong (chong gio anh in).
    2. Neu nguoi duoc bao ve da dat Mat ma gia dinh: nguoi bi chan phai tra loi dung (sai 3 lan -> that bai).
    3. Moi ben xem anh cua ben kia va xac nhan "Dung la nguoi than / nguoi quen cua toi".
Thanh cong: go chan, bo dem ve 0 -> Ve si theo doi lai tu dau (lai 3 lan lua dao thi chan lai).
Ket thuc (thanh cong / that bai / het han 24 gio): XOA anh, chi giu diem so + ket qua.
"""
from __future__ import annotations

import io
import random
import secrets
import shutil
import time
from datetime import timedelta
from pathlib import Path

from flask import current_app

from db.database import db, iso, utcnow
from db.models import Appeal, AppealCapture, Block, Conversation, GuardianEvent, ScamCounter, User
from services.chat_service import ChatError, guardian_block, user_dto
from services.notify import notify
from services.realtime import emit_to

EXPIRY = timedelta(hours=24)
MAX_APPEALS = 3                      # so lan khieu nai toi da cho moi lan bi chan
MAX_CAPTURE_TRIES = 3                # so lan chup lai (khong thay mat / khong chuyen dong) moi ben
MAX_QUESTION_TRIES = 3
CHALLENGE_TTL = 90                   # giay: phai chup trong thoi gian nay sau khi nhan thao tac
MIN_MOTION = 1.2                     # do chuyen dong toi thieu giua cac khung (chong gio anh)
MAX_FRAME_BYTES = 1_500_000
ACTIONS = ["Quay mặt sang TRÁI rồi nhìn thẳng lại", "Quay mặt sang PHẢI rồi nhìn thẳng lại", "Gật đầu chậm 2 lần",
           "Nghiêng đầu sang một bên rồi thẳng lại", "Mỉm cười rồi há miệng", "Đưa mặt lại gần camera rồi lùi ra"]
_challenges: dict[tuple[int, int], tuple[str, str, float]] = {}


# --------------------------------------------------------------------------- #
# Truy van
# --------------------------------------------------------------------------- #
def _block_for(appeal: Appeal) -> Block | None:
    return Block.query.filter_by(blocker_id=appeal.protected_id, blocked_id=appeal.accused_id, source="guardian").first()


def _appeals_since_block(protected_id: int, accused_id: int) -> list[Appeal]:
    b = Block.query.filter_by(blocker_id=protected_id, blocked_id=accused_id, source="guardian").first()
    q = Appeal.query.filter_by(protected_id=protected_id, accused_id=accused_id)
    if b is not None:
        # khieu nai THANH CONG luon thuoc lan chan da go (vong lap: chan lai -> 3 luot khieu nai moi)
        q = q.filter(Appeal.status != "success")
        q = q.filter(Appeal.created_at >= b.created_at - timedelta(seconds=1))
    return q.order_by(Appeal.id.desc()).all()


def appeal_summary(protected_id: int, accused_id: int, viewer_id: int) -> dict:
    rows = _appeals_since_block(protected_id, accused_id)
    for a in rows:
        _expire_if_needed(a)
    last = rows[0] if rows else None
    return {"id": last.id if last else None, "status": last.status if last else None,
            "fail_reason": last.fail_reason if last else None,
            "remaining": max(0, MAX_APPEALS - len(rows)), "can_open": (last is None or last.status != "open") and len(rows) < MAX_APPEALS}


def role(appeal: Appeal, uid: int) -> str:
    return "protected" if uid == appeal.protected_id else "accused"


def get_appeal(appeal_id: int, uid: int) -> Appeal:
    a = db.session.get(Appeal, appeal_id)
    if a is None or uid not in (a.protected_id, a.accused_id):
        raise ChatError("Không tìm thấy khiếu nại.", 404)
    _expire_if_needed(a)
    return a


def _captures(appeal: Appeal, uid: int) -> list[AppealCapture]:
    return AppealCapture.query.filter_by(appeal_id=appeal.id, user_id=uid).order_by(AppealCapture.id).all()


def _passed_capture(appeal: Appeal, uid: int) -> AppealCapture | None:
    return next((c for c in reversed(_captures(appeal, uid)) if c.passed), None)


def view(appeal: Appeal, viewer_id: int) -> dict:
    """Trang thai khieu nai tu goc nhin cua 1 ben."""
    me_role = role(appeal, viewer_id)
    other_id = appeal.accused_id if me_role == "protected" else appeal.protected_id
    other = db.session.get(User, other_id)
    mine, theirs = _passed_capture(appeal, viewer_id), _passed_capture(appeal, other_id)
    tries = len(_captures(appeal, viewer_id))
    my_conf = appeal.protected_confirm if me_role == "protected" else appeal.accused_confirm
    their_conf = appeal.accused_confirm if me_role == "protected" else appeal.protected_confirm
    protected = db.session.get(User, appeal.protected_id)
    can_see_other = appeal.status == "open" and mine is not None and theirs is not None
    return {
        "id": appeal.id, "status": appeal.status, "fail_reason": appeal.fail_reason, "role": me_role,
        "other": user_dto(other, viewer_id, with_presence=False), "conversation_id": appeal.conversation_id,
        "created_at": iso(appeal.created_at), "expires_at": iso(appeal.expires_at),
        "steps": {
            "my_capture": {"done": mine is not None, "tries": tries, "max_tries": MAX_CAPTURE_TRIES},
            "other_capture": {"done": theirs is not None},
            "question": {"required": appeal.question_required, "passed": appeal.question_passed,
                         "attempts": appeal.question_attempts, "max": MAX_QUESTION_TRIES,
                         "text": protected.family_question if (appeal.question_required and me_role == "accused") else None,
                         "i_answer": me_role == "accused"},
            "my_confirm": my_conf, "other_confirm": their_conf,
        },
        "other_photos": [f"/api/appeals/{appeal.id}/photo/{theirs.id}/{i}" for i in range(len(theirs.files or []))]
        if can_see_other else [],
    }


# --------------------------------------------------------------------------- #
# Mo khieu nai
# --------------------------------------------------------------------------- #
def open_appeal(user: User, other_id: int) -> Appeal:
    gb = guardian_block(user.id, other_id)
    if gb is None:
        raise ChatError("Không có lần chặn tự động nào để khiếu nại.", 404)
    rows = _appeals_since_block(gb.blocker_id, gb.blocked_id)
    for a in rows:
        _expire_if_needed(a)
    if any(a.status == "open" for a in rows):
        return next(a for a in rows if a.status == "open")
    if len(rows) >= MAX_APPEALS:
        raise ChatError(f"Đã hết {MAX_APPEALS} lần khiếu nại cho lần chặn này.", 403)
    protected = db.session.get(User, gb.blocker_id)
    lo, hi = sorted((gb.blocker_id, gb.blocked_id))
    conv = Conversation.query.filter_by(user_low_id=lo, user_high_id=hi).first()
    a = Appeal(protected_id=gb.blocker_id, accused_id=gb.blocked_id, opened_by=user.id,
               conversation_id=conv.id if conv else None, question_required=bool(protected.family_answer_hash),
               expires_at=utcnow() + EXPIRY)
    db.session.add(a)
    db.session.commit()
    other = other_id
    notify(other, "appeal", f"🛡️ {user.name} đã gửi KHIẾU NẠI gỡ chặn. Hai bạn cần chụp ảnh trực tiếp và xác nhận nhau "
                            f"trong 24 giờ.", link=f"/appeal/{a.id}", actor_id=user.id, level=1)
    _event(a, "open")
    _push(a)
    return a


# --------------------------------------------------------------------------- #
# Buoc 1: chup truc tiep (co mat + co cu dong)
# --------------------------------------------------------------------------- #
def new_challenge(appeal: Appeal, user: User) -> dict:
    _require_open(appeal)
    if _passed_capture(appeal, user.id):
        raise ChatError("Bạn đã chụp xong.")
    if len(_captures(appeal, user.id)) >= MAX_CAPTURE_TRIES:
        raise ChatError("Bạn đã hết lượt chụp.")
    nonce, action = secrets.token_hex(8), random.choice(ACTIONS)
    _challenges[(appeal.id, user.id)] = (nonce, action, time.time())
    return {"nonce": nonce, "action": action, "frames": 3, "seconds": 3}


def _motion(images) -> float:
    """Do khac biet trung binh giua cac khung lien tiep (anh xam 64x64, %) - nguoi that cu dong, anh in thi gan nhu dung yen."""
    import numpy as np
    arr = [np.asarray(im.convert("L").resize((64, 64)), dtype=np.float32) for im in images]
    diffs = [float(np.abs(arr[i] - arr[i - 1]).mean()) / 255 * 100 for i in range(1, len(arr))]
    return round(max(diffs) if diffs else 0.0, 3)


def submit_capture(appeal: Appeal, user: User, nonce: str, files: list) -> dict:
    from PIL import Image, UnidentifiedImageError

    from services.face_check import count_faces
    _require_open(appeal)
    ch = _challenges.pop((appeal.id, user.id), None)
    if ch is None or ch[0] != nonce or time.time() - ch[2] > CHALLENGE_TTL:
        raise ChatError("Phiên chụp đã hết hạn, hãy bấm chụp lại.")
    if _passed_capture(appeal, user.id):
        raise ChatError("Bạn đã chụp xong.")
    if len(files) != 3:
        raise ChatError("Cần đủ 3 khung hình chụp trực tiếp.")
    images, raw = [], []
    for f in files:
        data = f.read()
        if not data or len(data) > MAX_FRAME_BYTES:
            raise ChatError("Khung hình không hợp lệ.")
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except (UnidentifiedImageError, OSError):
            raise ChatError("Khung hình không hợp lệ.")
        images.append(im.convert("RGB"))
        raw.append(data)
    faces = count_faces(images)
    motion = _motion(images)
    cap = AppealCapture(appeal_id=appeal.id, user_id=user.id, action=ch[1], faces_found=faces, motion=motion)
    if faces < 2:
        cap.reason = "Không thấy rõ khuôn mặt (cần thấy mặt trong ít nhất 2/3 khung). Hãy nhìn thẳng camera, đủ sáng."
    elif motion < MIN_MOTION:
        cap.reason = "Không thấy cử động theo yêu cầu (có thể là ảnh tĩnh). Hãy làm đúng thao tác khi chụp."
    else:
        cap.passed = True
        folder = Path(current_app.config["UPLOAD_DIR"]) / "appeals" / str(appeal.id)
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for i, im in enumerate(images):
            name = f"{user.id}_{secrets.token_hex(6)}_{i}.jpg"
            im.thumbnail((640, 640))
            im.save(folder / name, "JPEG", quality=85)
            names.append(name)
        cap.files = names
    db.session.add(cap)
    db.session.commit()
    if not cap.passed and len(_captures(appeal, user.id)) >= MAX_CAPTURE_TRIES:
        _fail(appeal, f"{user.name} chụp xác minh không đạt sau {MAX_CAPTURE_TRIES} lần.")
    else:
        _try_complete(appeal)
        if appeal.status == "open":
            _push(appeal)
    return {"passed": cap.passed, "reason": cap.reason, "faces": faces, "motion": motion, "appeal": view(appeal, user.id)}


# --------------------------------------------------------------------------- #
# Buoc 2: Mat ma gia dinh  -  Buoc 3: hai ben xac nhan nhau
# --------------------------------------------------------------------------- #
def answer_question(appeal: Appeal, user: User, answer: str) -> dict:
    from werkzeug.security import check_password_hash

    from routes.settings import family_answer_key
    _require_open(appeal)
    if role(appeal, user.id) != "accused" or not appeal.question_required:
        raise ChatError("Bạn không cần trả lời câu hỏi.")
    if appeal.question_passed:
        return {"correct": True}
    protected = db.session.get(User, appeal.protected_id)
    ok = bool(answer and protected.family_answer_hash and check_password_hash(protected.family_answer_hash, family_answer_key(answer)))
    appeal.question_attempts += 1
    if ok:
        appeal.question_passed = True
    db.session.commit()
    if not ok and appeal.question_attempts >= MAX_QUESTION_TRIES:
        _fail(appeal, f"Trả lời sai Mật mã gia đình {MAX_QUESTION_TRIES} lần.")
    else:
        _try_complete(appeal)
        if appeal.status == "open":
            _push(appeal)
    return {"correct": ok, "attempts": appeal.question_attempts}


def confirm(appeal: Appeal, user: User, accept: bool) -> dict:
    _require_open(appeal)
    other = appeal.accused_id if role(appeal, user.id) == "protected" else appeal.protected_id
    if not (_passed_capture(appeal, user.id) and _passed_capture(appeal, other)):
        raise ChatError("Cả hai bên cần chụp xác minh xong trước khi xác nhận.")
    if role(appeal, user.id) == "protected":
        appeal.protected_confirm = accept
    else:
        appeal.accused_confirm = accept
    db.session.commit()
    if not accept:
        _fail(appeal, f"{user.name} xác nhận người trong ảnh KHÔNG phải người thân / người quen.")
    else:
        _try_complete(appeal)                    # hoan tat truoc (tu _push khi xong) -> ben kia khong tai anh vua bi xoa
        if appeal.status == "open":
            _push(appeal)
    return view(appeal, user.id)


# --------------------------------------------------------------------------- #
# Ket thuc
# --------------------------------------------------------------------------- #
def _require_open(appeal: Appeal):
    if appeal.status != "open":
        raise ChatError("Khiếu nại đã kết thúc.")


def _expire_if_needed(appeal: Appeal):
    if appeal.status == "open" and utcnow() > appeal.expires_at:
        appeal.status, appeal.fail_reason, appeal.closed_at = "expired", "Quá 24 giờ chưa hoàn tất xác minh.", utcnow()
        db.session.commit()
        _cleanup(appeal)


def _try_complete(appeal: Appeal):
    if appeal.status != "open":
        return
    if not (_passed_capture(appeal, appeal.protected_id) and _passed_capture(appeal, appeal.accused_id)):
        return
    if appeal.question_required and not appeal.question_passed:
        return
    if appeal.protected_confirm is not True or appeal.accused_confirm is not True:
        return
    _succeed(appeal)


def _succeed(appeal: Appeal):
    from services import chat_service as cs
    b = _block_for(appeal)
    if b is not None:
        db.session.delete(b)
    if appeal.conversation_id:                                       # bo dem ve 0 cho ca 2 chieu
        ScamCounter.query.filter_by(conversation_id=appeal.conversation_id).delete()
    appeal.status, appeal.closed_at = "success", utcnow()
    db.session.commit()
    cs._notify_block_change(appeal.protected_id, appeal.accused_id)
    p, a = db.session.get(User, appeal.protected_id), db.session.get(User, appeal.accused_id)
    for uid, other in ((p.id, a), (a.id, p)):
        notify(uid, "appeal", f"✅ Khiếu nại thành công: đã xác minh trực tiếp với {other.name}. Vệ sĩ đã GỠ CHẶN, "
                              f"hai bạn nhắn tin lại được. Vệ sĩ vẫn theo dõi lại từ đầu: nếu lại phát hiện lừa đảo 3 lần, "
                              f"sẽ tự động chặn lại.", link=f"/messages/{appeal.conversation_id}" if appeal.conversation_id
               else f"/appeal/{appeal.id}", actor_id=other.id, level=0)
    _event(appeal, "success")
    _cleanup(appeal)
    _push(appeal)


def _fail(appeal: Appeal, reason: str):
    appeal.status, appeal.fail_reason, appeal.closed_at = "failed", reason[:300], utcnow()
    db.session.commit()
    for uid in (appeal.protected_id, appeal.accused_id):
        notify(uid, "appeal", f"❌ Khiếu nại gỡ chặn THẤT BẠI: {reason} Vẫn giữ chặn.", link=f"/appeal/{appeal.id}",
               actor_id=None, level=1)
    _event(appeal, "failed")
    _cleanup(appeal)
    _push(appeal)


def _cleanup(appeal: Appeal):
    """Xoa anh chup (chi giu diem so + ket qua)."""
    folder = Path(current_app.config["UPLOAD_DIR"]) / "appeals" / str(appeal.id)
    shutil.rmtree(folder, ignore_errors=True)
    for c in AppealCapture.query.filter_by(appeal_id=appeal.id).all():
        c.files = None
    db.session.commit()


def photo_path(appeal: Appeal, capture_id: int, idx: int, viewer_id: int) -> Path:
    """Anh cua BEN KIA - chi xem duoc khi khieu nai dang mo va chinh minh da chup xong."""
    cap = db.session.get(AppealCapture, capture_id)
    if (cap is None or cap.appeal_id != appeal.id or cap.user_id == viewer_id or appeal.status != "open"
            or not _passed_capture(appeal, viewer_id) or not cap.files or not 0 <= idx < len(cap.files)):
        raise ChatError("Không xem được ảnh này.", 404)
    return Path(current_app.config["UPLOAD_DIR"]) / "appeals" / str(appeal.id) / cap.files[idx]


def _push(appeal: Appeal):
    for uid in (appeal.protected_id, appeal.accused_id):
        emit_to(uid, "appeal:update", {"appeal_id": appeal.id, "status": appeal.status})


def _event(appeal: Appeal, stage: str):
    from agents import orchestrator
    p = db.session.get(User, appeal.protected_id)
    caps = AppealCapture.query.filter_by(appeal_id=appeal.id).all()
    ev = GuardianEvent(model_key=p.model_key, kind="appeal", protected_id=appeal.protected_id, actor_id=appeal.accused_id,
                       level=0 if stage == "success" else (2 if stage == "failed" else 1),
                       results={"appeal": {"stage": stage, "status": appeal.status, "reason": appeal.fail_reason,
                                           "question_required": appeal.question_required,
                                           "question_passed": appeal.question_passed,
                                           "captures": [{"user": "protected" if c.user_id == appeal.protected_id else "accused",
                                                         "passed": c.passed, "faces": c.faces_found, "motion": c.motion,
                                                         "reason": c.reason} for c in caps]}},
                       modes={}, timings={})
    db.session.add(ev)
    db.session.commit()
    orchestrator._broadcast(ev)
