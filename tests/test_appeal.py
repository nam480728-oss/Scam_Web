"""Kiem thu: lan 3 tu dong chan + Khieu nai go chan (chup truc tiep co mat + cu dong, Mat ma gia dinh, 2 ben xac nhan)
+ vong lap: go chan xong lai 3 lan lua dao thi chan lai."""
import io
from datetime import timedelta
from pathlib import Path

import pytest
from PIL import Image

from db.database import db, utcnow
from db.models import Appeal, AppealCapture, Block, Notification, Report, ScamCounter

SCAM = "Bấm link này để nhận trúng thưởng nhé"


@pytest.fixture
def blocked(app, pair):
    """alice (nghi lua dao) gui 3 tin -> Ve si tu chan alice phia bob."""
    a, b, cid = pair
    for i in range(3):
        a.say(cid, SCAM + str(i))
    with app.app_context():
        assert Block.query.filter_by(blocker_id=b.id, blocked_id=a.id, source="guardian").count() == 1
    return a, b, cid


@pytest.fixture
def stills(monkeypatch):
    """Gia lap so khung co khuon mat (khong can webcam / mat that trong test)."""
    from services import face_check
    state = {"faces": 3}
    monkeypatch.setattr(face_check, "count_faces", lambda images: state["faces"])
    return state


def frames(seed=0):
    out = []
    for i in range(3):                                                # 3 khung khac nhau -> co chuyen dong
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), ((seed * 40 + i * 70) % 255, 120, 200 - i * 50)).save(buf, "JPEG")
        out.append(buf.getvalue())
    return out


def capture(actor, aid, imgs=None):
    ch = actor.post(f"/api/appeals/{aid}/challenge").get_json()
    data = {"nonce": ch["nonce"], **{f"frame{i}": (io.BytesIO(f), f"f{i}.jpg") for i, f in enumerate(imgs or frames())}}
    return actor.client.post(f"/api/appeals/{aid}/capture", data=data, content_type="multipart/form-data").get_json()


def test_appeal_success_unblocks_and_resets(app, blocked, stills, mk):
    a, b, cid = blocked
    r = a.post("/api/appeals", {"user_id": b.id})                     # nguoi BI CHAN mo khieu nai
    assert r.status_code == 201
    aid = r.get_json()["appeal"]["id"]
    assert b.post("/api/appeals", {"user_id": a.id}).get_json()["appeal"]["id"] == aid     # dang mo -> dung lai
    assert mk("carol").get(f"/api/appeals/{aid}").status_code == 404   # nguoi ngoai khong xem duoc
    assert a.post(f"/api/appeals/{aid}/confirm", {"accept": True}).status_code == 400      # chua chup
    ra = capture(a, aid)
    assert ra["passed"] and ra["appeal"]["steps"]["my_capture"]["done"]
    v = b.get(f"/api/appeals/{aid}").get_json()["appeal"]
    assert v["role"] == "protected" and v["other_photos"] == []       # chua chup thi chua thay anh ben kia
    rb = capture(b, aid)
    assert rb["passed"]
    v = b.get(f"/api/appeals/{aid}").get_json()["appeal"]
    assert len(v["other_photos"]) == 3
    assert b.get(v["other_photos"][0]).status_code == 200              # xem anh cua ben kia
    with app.app_context():
        own = AppealCapture.query.filter_by(appeal_id=aid, user_id=b.id).one()
    assert b.get(f"/api/appeals/{aid}/photo/{own.id}/0").status_code == 404   # khong qua route nay cho anh cua minh
    b.post(f"/api/appeals/{aid}/confirm", {"accept": True})
    v = a.post(f"/api/appeals/{aid}/confirm", {"accept": True}).get_json()["appeal"]
    assert v["status"] == "success"
    with app.app_context():
        assert Block.query.count() == 0                                  # da go chan
        assert ScamCounter.query.filter_by(conversation_id=cid).count() == 0      # bo dem ve 0
        assert Report.query.filter_by(reported_id=a.id, source="auto").count() == 0
        assert all(c.files is None for c in AppealCapture.query.all())   # anh da xoa
        assert not (Path(app.config["UPLOAD_DIR"]) / "appeals" / str(aid)).exists()
        assert Notification.query.filter_by(kind="appeal", user_id=b.id).count() >= 1
    assert a.say(cid, "Mẹ ơi con đây").status_code == 201              # nhan tin lai duoc


def test_appeal_three_bad_captures_fails_and_keeps_block(app, blocked, stills):
    a, b, cid = blocked
    aid = a.post("/api/appeals", {"user_id": b.id}).get_json()["appeal"]["id"]
    stills["faces"] = 0                                                 # khong lo mat (vd che camera / anh khong co nguoi)
    for _ in range(3):
        r = capture(a, aid)
        assert not r["passed"] and "khuôn mặt" in r["reason"]
    v = a.get(f"/api/appeals/{aid}").get_json()["appeal"]
    assert v["status"] == "failed" and "3 lần" in v["fail_reason"]
    with app.app_context():
        assert Block.query.filter_by(source="guardian").count() == 1     # van chan
    assert a.post(f"/api/appeals/{aid}/challenge").status_code == 400  # khieu nai da ket thuc
    s = b.get(f"/api/conversations/{cid}").get_json()["conversation"]["guardian_block"]["appeal"]
    assert s["status"] == "failed" and s["remaining"] == 2 and s["can_open"] is True


def test_face_check_counts_real_faces():
    """OpenCV Haar: anh khong co mat -> 0 khung."""
    from PIL import Image as Img

    from services.face_check import count_faces
    assert count_faces([Img.new("RGB", (320, 240), (120, 120, 120))] * 3) == 0


def test_appeal_liveness_retry_question_and_limits(app, blocked, stills):
    a, b, cid = blocked
    assert b.post("/api/settings/family", {"question": "Tên con chó nhà mình?", "answer": "Mực"}).status_code == 200
    aid = b.post("/api/appeals", {"user_id": a.id}).get_json()["appeal"]["id"]   # nguoi DUOC BAO VE mo
    same = frames()[0]
    r = capture(a, aid, imgs=[same, same, same])                        # anh dung yen -> khong chuyen dong
    assert not r["passed"] and "cử động" in r["reason"]
    stills["faces"] = 1
    r = capture(a, aid)
    assert not r["passed"] and "khuôn mặt" in r["reason"]
    stills["faces"] = 3
    assert capture(a, aid)["passed"] and capture(b, aid)["passed"]
    q = a.get(f"/api/appeals/{aid}").get_json()["appeal"]["steps"]["question"]
    assert q["required"] and q["text"] == "Tên con chó nhà mình?" and q["i_answer"]
    assert b.get(f"/api/appeals/{aid}").get_json()["appeal"]["steps"]["question"]["text"] is None
    assert a.post(f"/api/appeals/{aid}/answer", {"answer": "Vàng"}).get_json()["correct"] is False
    assert a.post(f"/api/appeals/{aid}/answer", {"answer": "  mực "}).get_json()["correct"] is True
    a.post(f"/api/appeals/{aid}/confirm", {"accept": True})
    v = b.post(f"/api/appeals/{aid}/confirm", {"accept": False}).get_json()["appeal"]   # nguoi duoc bao ve tu choi
    assert v["status"] == "failed"
    # het han
    aid2 = a.post("/api/appeals", {"user_id": b.id}).get_json()["appeal"]["id"]
    with app.app_context():
        db.session.get(Appeal, aid2).expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
    assert a.get(f"/api/appeals/{aid2}").get_json()["appeal"]["status"] == "expired"
    # lan 3 roi het luot
    aid3 = a.post("/api/appeals", {"user_id": b.id}).get_json()["appeal"]["id"]
    for _ in range(3):                                                  # sai Mat ma 3 lan -> that bai
        a.post(f"/api/appeals/{aid3}/answer", {"answer": "sai"})
    assert a.get(f"/api/appeals/{aid3}").get_json()["appeal"]["status"] == "failed"
    r = a.post("/api/appeals", {"user_id": b.id})
    assert r.status_code == 403 and "hết" in r.get_json()["error"]
    assert b.delete(f"/api/blocks/{a.id}").status_code == 403           # van khong go bang nut Bo chan


def test_appeal_requires_guardian_block(pair):
    a, b, cid = pair
    assert a.post("/api/appeals", {"user_id": b.id}).status_code == 404
    b.post("/api/blocks", {"user_id": a.id})                            # chan tay: khong khieu nai duoc
    assert a.post("/api/appeals", {"user_id": b.id}).status_code == 404


def run_appeal(a, b, aid):
    assert capture(a, aid)["passed"] and capture(b, aid)["passed"]
    b.post(f"/api/appeals/{aid}/confirm", {"accept": True})
    return a.post(f"/api/appeals/{aid}/confirm", {"accept": True}).get_json()["appeal"]["status"]


def test_loop_after_appeal_blocks_again(app, blocked, stills):
    """Go chan xong Ve si theo doi lai TU DAU: lan 1 -> lan 2 (che) -> lan 3 chan lai; moi lan chan co lai 3 luot khieu nai."""
    a, b, cid = blocked
    for round_no in (2, 3):
        aid = a.post("/api/appeals", {"user_id": b.id}).get_json()["appeal"]["id"]
        assert run_appeal(a, b, aid) == "success"
        levels = []
        for i in range(3):
            mid = a.say(cid, SCAM + f" vong {round_no} tin {i}").get_json()["message"]["id"]
            with app.app_context():
                from db.models import Message
                levels.append(db.session.get(Message, mid).warning_level)
        assert levels == [1, 2, 3]                                      # bat dau lai tu lan 1
        with app.app_context():
            blk = Block.query.filter_by(blocker_id=b.id, blocked_id=a.id, source="guardian").one()
            assert f"lần chặn thứ {round_no}" in blk.reason
            assert Notification.query.filter(Notification.user_id == a.id, Notification.kind == "guardian_block",
                                             Notification.text.like(f"%lần chặn thứ {round_no}%")).count() == 1
        assert a.say(cid, "còn đó không").status_code == 403            # bi chan lai
        s = b.get(f"/api/conversations/{cid}").get_json()["conversation"]["guardian_block"]["appeal"]
        assert s["remaining"] == 3 and s["can_open"] is True and s["id"] is None    # luot khieu nai tinh lai cho lan chan moi
