"""Kiem thu tinh nang chat moi: tra loi trich dan, thu hoi, tha cam xuc, ghim tin, tim trong hoi thoai, kho anh / tep / link,
tin nhan thoai (va luat che tin thoai / anh khi nguoi gui da bi canh bao tu lan 2)."""
import io

import pytest
from PIL import Image

from db.database import db, utcnow
from db.models import Message, MessageReaction, ScamCounter

SCAM = "Chuyển khoản gấp vào stk 99990008889990, khẩn cấp lắm"


@pytest.fixture
def sio(app):
    from services.realtime import socketio
    clients = []

    def connect(actor):
        c = socketio.test_client(app, flask_test_client=actor.client)
        clients.append(c)
        return c
    yield connect
    for c in clients:
        if c.is_connected():
            c.disconnect()


def msgs(actor, cid, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return actor.get(f"/api/conversations/{cid}/messages" + (f"?{q}" if q else "")).get_json()["messages"]


def voice(actor, cid, seconds=3.2, **extra):
    data = {"voice": (io.BytesIO(b"\x1aE\xdf\xa3 webm gia lap"), "ghi-am.webm"), "duration": str(seconds), **extra}
    return actor.client.post(f"/api/conversations/{cid}/messages", data=data, content_type="multipart/form-data")


def image(actor, cid, body=None):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 50, 50)).save(buf, "PNG")
    data = {"file": (io.BytesIO(buf.getvalue()), "anh.png")}
    if body:
        data["body"] = body
    return actor.client.post(f"/api/conversations/{cid}/messages", data=data, content_type="multipart/form-data")


def test_reply_quote_and_masked_quote(app, pair, mk):
    a, b, cid = pair
    first = a.say(cid, "Mai đi cà phê không?").get_json()["message"]
    r = b.say(cid, "Ok 7h nhé", reply_to_id=first["id"]).get_json()["message"]
    assert r["reply_to"] == {"id": first["id"], "sender_id": a.id, "mine": False, "kind": "text", "preview": "Mai đi cà phê không?"}
    assert msgs(a, cid)[-1]["reply_to"]["mine"] is True
    c = mk("carol")
    cid2 = c.conv_with(a)
    other = c.say(cid2, "tin o cuoc chat khac").get_json()["message"]
    assert b.say(cid, "x", reply_to_id=other["id"]).status_code == 404       # khong tra loi tin cua cuoc chat khac
    assert b.say(cid, "x", reply_to_id="abc").status_code == 400
    # tra loi mot tin bi Ve si che -> trich dan cung bi che voi nguoi nhan
    s = mk("scammer")
    cid3 = s.conv_with(b)
    s.say(cid3, SCAM)
    m2 = s.say(cid3, SCAM + " nhé").get_json()["message"]
    q = b.say(cid3, "Gì vậy?", reply_to_id=m2["id"]).get_json()["message"]
    assert "che" in q["reply_to"]["preview"] and "99990008889990" not in q["reply_to"]["preview"]


def test_recall_hides_for_both_but_keeps_warning(app, pair, mk, sio):
    a, b, cid = pair
    cb = sio(b)
    m = a.say(cid, "Tin nhắn gửi nhầm").get_json()["message"]
    assert m["can_recall"] is True
    assert b.post(f"/api/messages/{m['id']}/recall").status_code == 403         # khong thu hoi tin cua nguoi khac
    r = a.post(f"/api/messages/{m['id']}/recall").get_json()["message"]
    assert r["recalled"] and r["body"] is None and not r["can_recall"]
    seen = msgs(b, cid)[-1]
    assert seen["recalled"] and seen["body"] is None
    assert any(e["name"] == "message:update" for e in cb.get_received())
    assert a.get(f"/api/conversations/{cid}").get_json()["conversation"]["last_message"]["preview"] == "Tin nhắn đã bị thu hồi"
    # qua 24 gio thi khong thu hoi duoc
    old = a.say(cid, "tin cu").get_json()["message"]
    with app.app_context():
        db.session.get(Message, old["id"]).created_at = utcnow().replace(year=2020)
        db.session.commit()
    assert a.post(f"/api/messages/{old['id']}/recall").status_code == 400
    # tin lua dao bi thu hoi: VAN tinh lan, nguoi nhan van thay muc canh bao; tep dinh kem khong tai duoc nua
    s = mk("scammer")
    cid2 = s.conv_with(b)
    sm = s.say(cid2, SCAM).get_json()["message"]
    s.post(f"/api/messages/{sm['id']}/recall")
    got = msgs(b, cid2)[-1]
    assert got["recalled"] and got["warning_level"] == 1 and got["body"] is None
    with app.app_context():
        assert ScamCounter.query.filter_by(conversation_id=cid2, user_id=s.id).one().flagged_count == 1
    img = image(a, cid).get_json()["message"]
    a.post(f"/api/messages/{img['id']}/recall")
    assert b.get(img["attachment"]["url"]).status_code == 404


def test_reactions_toggle_and_permissions(app, pair, mk):
    a, b, cid = pair
    m = a.say(cid, "Hôm nay vui quá").get_json()["message"]
    r = b.post(f"/api/messages/{m['id']}/react", {"emoji": "❤️"}).get_json()["message"]
    assert r["reactions"] == {"counts": {"❤️": 1}, "mine": "❤️"}
    a.post(f"/api/messages/{m['id']}/react", {"emoji": "😂"})
    got = msgs(a, cid)[-1]["reactions"]
    assert got["counts"] == {"❤️": 1, "😂": 1} and got["mine"] == "😂"
    r = b.post(f"/api/messages/{m['id']}/react", {"emoji": "👍"}).get_json()["message"]      # doi cam xuc
    assert r["reactions"]["counts"] == {"😂": 1, "👍": 1}
    r = b.post(f"/api/messages/{m['id']}/react", {"emoji": "👍"}).get_json()["message"]      # bam lai = go
    assert r["reactions"] == {"counts": {"😂": 1}, "mine": None}
    assert b.post(f"/api/messages/{m['id']}/react", {"emoji": "🍕"}).status_code == 400
    assert mk("carol").post(f"/api/messages/{m['id']}/react", {"emoji": "❤️"}).status_code == 404
    b.post("/api/blocks", {"user_id": a.id})
    assert a.post(f"/api/messages/{m['id']}/react", {"emoji": "❤️"}).status_code == 403    # bi chan thi khong tha duoc
    with app.app_context():
        assert MessageReaction.query.count() == 1


def test_pin_max_three_and_jump_around(app, pair):
    a, b, cid = pair
    ids = [a.say(cid, f"tin {i}").get_json()["message"]["id"] for i in range(60)]
    for i in ids[:3]:
        assert b.post(f"/api/messages/{i}/pin", {"pinned": True}).status_code == 200
    assert b.post(f"/api/messages/{ids[3]}/pin", {"pinned": True}).status_code == 400       # toi da 3
    pinned = a.get(f"/api/conversations/{cid}").get_json()["conversation"]["pinned"]
    assert [p["id"] for p in pinned] == ids[:3][::-1] and pinned[0]["mine"] is True
    assert msgs(a, cid, around=ids[0])[0]["pinned"] is True                                # nhay toi tin cu
    page = a.get(f"/api/conversations/{cid}/messages?around={ids[20]}").get_json()
    assert page["messages"][0]["id"] == ids[5] and page["messages"][-1]["id"] == ids[-1] and page["has_more"] is True
    b.post(f"/api/messages/{ids[0]}/pin", {"pinned": False})
    assert len(a.get(f"/api/conversations/{cid}").get_json()["conversation"]["pinned"]) == 2
    a.post(f"/api/messages/{ids[1]}/recall")                                               # thu hoi -> bo ghim
    assert len(a.get(f"/api/conversations/{cid}").get_json()["conversation"]["pinned"]) == 1


def test_search_and_media_gallery(app, pair, mk):
    a, b, cid = pair
    a.say(cid, "Hẹn gặp ở quán Cà Phê Muối nhé")
    b.say(cid, "xem video này https://www.youtube.com/watch?v=abc")
    rec = a.say(cid, "cà phê sữa đá").get_json()["message"]
    a.post(f"/api/messages/{rec['id']}/recall")
    image(a, cid, body="ảnh quán cà phê")
    a.client.post(f"/api/conversations/{cid}/messages", data={"file": (io.BytesIO(b"%PDF-1.4"), "thuc-don.pdf")},
                  content_type="multipart/form-data")
    res = b.get(f"/api/conversations/{cid}/search?q=cà phê").get_json()["results"]
    assert len(res) == 2 and all("cà phê" in r["preview"].lower() for r in res)            # khong tim tin da thu hoi
    assert b.get(f"/api/conversations/{cid}/search?q=a").get_json()["results"] == []
    assert mk("carol").get(f"/api/conversations/{cid}/search?q=cà phê").status_code == 404
    imgs = b.get(f"/api/conversations/{cid}/media?kind=images").get_json()["items"]
    files = b.get(f"/api/conversations/{cid}/media?kind=files").get_json()["items"]
    links = a.get(f"/api/conversations/{cid}/media?kind=links").get_json()["items"]
    assert len(imgs) == 1 and imgs[0]["url"] and not imgs[0]["hidden"]
    assert [f["name"] for f in files] == ["thuc-don.pdf"]
    assert links[0]["url"] == "https://www.youtube.com/watch?v=abc" and links[0]["danger"] is False
    assert b.get(f"/api/conversations/{cid}/media?kind=xyz").status_code == 400


def test_voice_message_and_mask_after_second_strike(app, pair, mk):
    a, b, cid = pair
    r = voice(a, cid)
    assert r.status_code == 201
    m = r.get_json()["message"]
    assert m["kind"] == "voice" and m["attachment"]["duration"] == 3.2 and m["body"] is None
    got = msgs(b, cid)[-1]
    assert got["warning_level"] == 0 and got["attachment"]["masked"] is False
    audio = b.get(got["attachment"]["url"])
    assert audio.status_code == 200 and audio.mimetype == "audio/webm" and "attachment" not in audio.headers.get("Content-Disposition", "")
    assert voice(a, cid, seconds=0.1).status_code == 400                     # qua ngan
    assert voice(a, cid, seconds=500).status_code == 400                     # qua 2 phut
    assert a.client.post(f"/api/conversations/{cid}/messages", data={"voice": (io.BytesIO(b"x"), "a.exe"), "duration": "3"},
                         content_type="multipart/form-data").status_code == 400
    # nguoi la da bi canh bao 2 lan: tin thoai / anh khong kem chu bi CHE nhung KHONG tinh them lan
    s = mk("scammer")
    cid2 = s.conv_with(b)
    s.say(cid2, SCAM)
    v1 = voice(s, cid2).get_json()["message"]
    assert msgs(b, cid2)[-1]["warning_level"] == 0                             # moi lan 1: tin thoai chua bi che
    s.say(cid2, SCAM + " nhé")
    voice(s, cid2)
    image(s, cid2)
    got = msgs(b, cid2)
    vm, im = got[-2], got[-1]
    assert vm["guard"]["mask"] and vm["guard"]["unreadable"] == "voice" and vm["attachment"]["masked"] is True
    assert im["guard"]["mask"] and im["guard"]["unreadable"] == "image"
    with app.app_context():
        assert ScamCounter.query.filter_by(conversation_id=cid2, user_id=s.id).one().flagged_count == 2
    assert [x for x in got if x["id"] == v1["id"]][0]["warning_level"] == 0
    assert b.get(f"/api/conversations/{cid2}").get_json()["conversation"]["last_message"]["preview"].startswith("🛡️")
