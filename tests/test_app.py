"""Kiem thu tu dong: xac thuc, ban be, chat, AI 3 muc canh bao, chan, dinh kem, realtime."""
import io

import pytest

from db.database import db
from tests.conftest import FakePredictor
from db.models import Block, FeedPost, Message, ScamCounter, User

SCAM = "Bấm link này để nhận trúng thưởng nhé"
OK = "Chiều nay đi ăn cơm không?"


# ------------------------------------------------------------------ cong chon mo hinh / xac thuc
def test_login_requires_model(app):
    from services.ai_client import manager
    manager.set_predictor(None, None)
    manager._predictor = None
    manager.active = None
    c = app.test_client()
    for url in ("/login", "/register", "/feed", "/messages"):
        r = c.get(url)
        assert r.status_code == 302 and r.headers["Location"].endswith("/"), url
    r = c.get("/api/conversations")
    assert r.status_code in (401, 503)
    assert c.get("/").status_code == 200                                # chua co mo hinh -> man hinh chon


def test_select_page_first_time_only(app):
    from services.ai_client import manager
    manager._predictor, manager.active = None, None
    c = app.test_client()
    r = c.get("/")                                                   # chua co mo hinh: man hinh chon (chu phan mem)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for name in ("TF-IDF + Linear SVM", "PhoBERT-base-v2", "ViSoBERT"):
        assert name in html
    d = c.get("/api/models").get_json()
    assert {m["key"] for m in d["models"]} == {"svm", "phobert", "viso"}
    assert c.post("/api/models/select/khong-co").status_code == 404
    manager.set_predictor("svm", FakePredictor())
    r = c.get("/")                                                   # da co mo hinh: nguoi dung vao thang trang dang nhap
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    r = c.post("/api/models/select/phobert")                         # nguoi dung thuong khong duoc doi mo hinh
    assert r.status_code == 403
    assert manager.active == "svm"


def test_admin_can_switch_model(app, monkeypatch):
    from services import ai_client
    from services.ai_client import manager
    c = app.test_client()
    assert c.get("/admin").status_code == 200 and "Mật khẩu quản trị" in c.get("/admin").get_data(as_text=True)
    r = c.post("/admin", data={"password": "sai"})
    assert r.status_code == 401
    assert c.post("/api/models/select/phobert").status_code == 403   # chua la quan tri
    r = c.post("/admin", data={"password": app.config["ADMIN_PASSWORD"]})
    assert r.status_code == 302
    assert "Quản trị" in c.get("/admin").get_data(as_text=True) and "PhoBERT-base-v2" in c.get("/admin").get_data(as_text=True)
    monkeypatch.setattr(ai_client, "_build", lambda key, spec: FakePredictor())
    changed = []
    manager.on_change = lambda key: changed.append(key)
    try:
        assert c.post("/api/models/select/phobert").status_code == 200
        import time
        for _ in range(100):
            if not manager.status()["loading"]:
                break
            time.sleep(0.05)
        assert manager.active == "phobert" and manager.status()["error"] is None and changed == ["phobert"]
    finally:
        manager.on_change = lambda key: __import__("services.realtime", fromlist=["socketio"]).socketio.emit(
            "system:model_changed", {"model": key})
        manager.set_predictor("svm", FakePredictor())
    assert c.post("/admin/logout").status_code == 302
    assert c.post("/api/models/select/svm").status_code == 403


def test_register_validation(app):
    c = app.test_client()
    name = {"display_name": "Nguyễn Văn Nam"}
    bad = [({**name, "username": "ab", "password": "matkhau1", "confirm": "matkhau1"}, "3–30"),
           ({**name, "username": "co dau ế", "password": "matkhau1", "confirm": "matkhau1"}, "3–30"),
           ({**name, "username": "validuser", "password": "123", "confirm": "123"}, "6 ký tự"),
           ({**name, "username": "validuser", "password": "matkhau1", "confirm": "khac1234"}, "không khớp"),
           ({"display_name": "A", "username": "validuser", "password": "matkhau1", "confirm": "matkhau1"}, "Họ tên"),
           ({**name, "username": "validuser", "phone": "12345", "password": "matkhau1", "confirm": "matkhau1"}, "Số điện thoại")]
    for data, msg in bad:
        r = c.post("/register", data=data)
        assert r.status_code == 200 and msg in r.get_data(as_text=True), data
    r = c.post("/register", data={**name, "username": "Nam_01", "password": "matkhau1", "confirm": "matkhau1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/feed")
    r = app.test_client().post("/register", data={**name, "username": "nam_01", "password": "matkhau1", "confirm": "matkhau1"})
    assert "đã tồn tại" in r.get_data(as_text=True)                    # trung ten khong phan biet hoa thuong
    with app.app_context():
        u = User.query.filter_by(username="Nam_01").one()
        assert u.display_name == "Nguyễn Văn Nam" and "nguyen van nam" in u.search_name


def test_login_logout_and_safe_next(app, mk):
    mk("carol")
    c = app.test_client()
    assert "không đúng" in c.post("/login", data={"username": "carol", "password": "sai"}).get_data(as_text=True)
    assert "không đúng" in c.post("/login", data={"username": "ghost", "password": "matkhau1"}).get_data(as_text=True)
    r = c.post("/login?next=https://evil.example/x", data={"username": "CAROL", "password": "matkhau1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/feed")      # khong open-redirect
    r = c.post("/logout")
    assert r.status_code == 302
    assert c.get("/feed").status_code == 302


def test_feed(app, mk):
    from services.seed_feed import seed_feed
    a = mk("alice")
    with app.app_context():
        assert seed_feed() == 18 and FeedPost.query.count() == 18
        assert seed_feed() == 0                                    # khong nhan doi
    html = a.get("/feed").get_data(as_text=True)
    import json
    import re
    items = json.loads(re.search(r'id="posts-data">(.*?)</script>', html, re.S).group(1))
    assert len(items) == 18 and any(it["author"]["name"] == "Hội Cảnh Giác Mạng" and it["fake"] for it in items)
    assert "Tin nhắn" in html


def test_csrf_enforced(app, mk):
    mk("alice")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        r = app.test_client().post("/login", data={"username": "alice", "password": "matkhau1"})
        assert r.status_code == 400
        r = app.test_client().post("/api/models/select/svm")
        assert r.status_code == 400 and r.get_json()["code"] == "csrf"
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


# ------------------------------------------------------------------ ban be
def test_friend_flow(mk):
    a, b, c = mk("alice"), mk("bob"), mk("carol")
    s = a.get("/api/users/search?q=BO").get_json()["users"]
    assert [u["username"] for u in s] == ["bob"] and s[0]["relation"] == "none"
    assert a.get("/api/users/search?q=alice").get_json()["users"] == []          # khong tim thay chinh minh
    assert a.get("/api/users/search?q=%25").get_json()["users"] == []            # ky tu dac biet khong khop het
    assert a.post("/api/friend-requests", {"user_id": a.id}).status_code == 400
    assert a.post("/api/friend-requests", {"user_id": 9999}).status_code == 404
    assert a.post("/api/friend-requests", {"user_id": "x"}).status_code == 400
    assert a.post("/api/friend-requests", {"user_id": b.id}).status_code == 201
    assert a.post("/api/friend-requests", {"user_id": b.id}).status_code == 400   # gui trung
    assert a.get("/api/users/search?q=bob").get_json()["users"][0]["relation"] == "sent"
    assert b.get("/api/users/search?q=alice").get_json()["users"][0]["relation"] == "received"
    rid = b.get("/api/friend-requests").get_json()["incoming"][0]["id"]
    assert a.post(f"/api/friend-requests/{rid}/accept").status_code == 404        # chi nguoi nhan moi duoc chap nhan
    assert c.post(f"/api/friend-requests/{rid}/accept").status_code == 404
    assert b.post(f"/api/friend-requests/{rid}/decline").status_code == 200
    assert a.post("/api/conversations", {"user_id": b.id}).status_code == 200     # nguoi la van nhan tin duoc (tin nhan cho)
    assert b.post("/api/friend-requests", {"user_id": a.id}).status_code == 201   # moi lai sau khi bi tu choi
    rid = a.get("/api/friend-requests").get_json()["incoming"][0]["id"]
    assert a.post(f"/api/friend-requests/{rid}/accept").status_code == 200
    assert [u["username"] for u in a.get("/api/friends").get_json()["friends"]] == ["bob"]
    assert a.post("/api/friend-requests", {"user_id": b.id}).status_code == 400   # da la ban
    # hai ben cung moi nhau -> tu dong thanh ban
    assert a.post("/api/friend-requests", {"user_id": c.id}).status_code == 201
    assert c.post("/api/friend-requests", {"user_id": a.id}).get_json()["status"] == "friend"
    # huy loi moi + huy ket ban
    d = mk("dave")
    assert a.post("/api/friend-requests", {"user_id": d.id}).status_code == 201
    out = a.get("/api/friend-requests").get_json()["outgoing"][0]["id"]
    assert d.delete(f"/api/friend-requests/{out}").status_code == 404
    assert a.delete(f"/api/friend-requests/{out}").status_code == 200
    assert a.delete(f"/api/friends/{b.id}").status_code == 200
    assert a.delete(f"/api/friends/{b.id}").status_code == 404


def test_conversation_access(pair, mk):
    a, b, cid = pair
    c = mk("carol")
    assert c.get(f"/api/conversations/{cid}").status_code == 404
    assert c.get(f"/api/conversations/{cid}/messages").status_code == 404
    assert c.say(cid, "xin chào").status_code == 404
    assert c.post(f"/api/conversations/{cid}/read").status_code == 404
    assert a.conv_with(b) == cid == b.conv_with(a)                  # moi cap chi 1 cuoc chat


# ------------------------------------------------------------------ chat co ban
def test_send_receive_history_unread(pair):
    a, b, cid = pair
    assert a.say(cid, "   ").status_code == 400
    assert a.say(cid, "x" * 2001).status_code == 400
    assert a.post(f"/api/conversations/{cid}/messages", {"body": 123}).status_code == 400
    for i in range(45):
        assert a.say(cid, f"tin {i}").status_code == 201
    convs = b.get("/api/conversations").get_json()["conversations"]
    assert convs[0]["unread"] == 45 and convs[0]["last_message"]["preview"] == "tin 44"
    assert a.get("/api/conversations").get_json()["conversations"][0]["unread"] == 0
    page1 = b.get(f"/api/conversations/{cid}/messages").get_json()
    assert len(page1["messages"]) == 40 and page1["has_more"] is True
    assert [m["body"] for m in page1["messages"]][-1] == "tin 44"
    first = page1["messages"][0]["id"]
    page2 = b.get(f"/api/conversations/{cid}/messages?before={first}").get_json()
    assert len(page2["messages"]) == 5 and page2["has_more"] is False
    assert b.post(f"/api/conversations/{cid}/read").get_json()["marked"] == 45
    assert b.get("/api/conversations").get_json()["conversations"][0]["unread"] == 0
    assert b.post(f"/api/conversations/{cid}/read").get_json()["marked"] == 0
    msgs = a.get(f"/api/conversations/{cid}/messages").get_json()["messages"]
    assert all(m["read_at"] for m in msgs)                          # nguoi gui thay "da xem"
    # tin trong cuoc chat khac khong lan sang
    assert a.get("/api/summary").get_json()["unread_total"] == 0


def test_unicode_and_xss_stored_safely(pair):
    a, b, cid = pair
    body = "<script>alert(1)</script> Xin chào 😀 tiếng Việt có dấu"
    assert a.say(cid, body).status_code == 201
    assert b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]["body"] == body


# ------------------------------------------------------------------ AI 3 muc canh bao
def test_three_strikes_mask_then_auto_block(app, pair):
    """Lan 1: canh bao (tin van hien) · Lan 2: che tin · Lan 3: TU DONG CHAN + bao ca 2 ben (go chi qua Khieu nai)."""
    a, b, cid = pair
    got = []
    for i in range(3):
        r = a.say(cid, SCAM + str(i)).get_json()["message"]
        assert r["warning_level"] == 0 and "guard" not in r          # nguoi gui khong thay co cua chinh minh
        got.append(b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1])
    assert [m["warning_level"] for m in got] == [1, 2, 3]
    assert [m["guard"]["mask"] for m in got] == [False, True, True]  # lan 2 tro di: che noi dung
    with app.app_context():
        blk = Block.query.one()
        assert (blk.blocker_id, blk.blocked_id, blk.source) == (b.id, a.id, "guardian")
        kinds = {(n.user_id, n.kind) for n in __import__("db.models", fromlist=["Notification"]).Notification.query.all()}
        assert (b.id, "guardian_block") in kinds and (a.id, "guardian_block") in kinds      # bao ca 2 ben
    r = a.say(cid, OK)                                                 # nguoi gui bi chan
    assert r.status_code == 403 and "Khiếu nại" in r.get_json()["error"]
    cb = b.get(f"/api/conversations/{cid}").get_json()["conversation"]
    ca = a.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert cb["guardian_block"]["role"] == "protected" and cb["guardian_block"]["appeal"]["can_open"] is True
    assert ca["guardian_block"]["role"] == "accused" and ca["self_warning"] is True
    assert cb["warning"] == 3 and cb["self_warning"] is False
    r = b.delete(f"/api/blocks/{a.id}")                                # khong go bang nut Bo chan
    assert r.status_code == 403 and "Khiếu nại" in r.get_json()["error"]
    assert b.get("/api/blocks").get_json()["blocked"][0]["block_source"] == "guardian"
    assert all(m["warning_level"] == 0 for m in a.get(f"/api/conversations/{cid}/messages").get_json()["messages"])
    with app.app_context():
        assert ScamCounter.query.filter_by(conversation_id=cid, user_id=a.id).one().flagged_count == 3


def test_warning_levels_1_and_2_hidden_from_sender(pair):
    a, b, cid = pair
    for expected in (1, 2):
        a.say(cid, SCAM)
        assert a.get(f"/api/conversations/{cid}").get_json()["conversation"]["self_warning"] is False
        assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == expected


def test_counters_per_sender_and_per_conversation(pair, mk):
    a, b, cid = pair
    c = mk("carol")
    a.befriend(c)
    cid2 = a.conv_with(c)
    for _ in range(2):
        a.say(cid, SCAM)
    a.say(cid2, SCAM)                                                  # cuoc chat khac: bo dem rieng -> lan 1
    assert c.get(f"/api/conversations/{cid2}").get_json()["conversation"]["warning"] == 1
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == 2
    # bob nhan lai: bo dem cua bob rieng biet
    b.say(cid, SCAM)
    assert a.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == 1
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == 2


def test_attachment_caption_is_moderated_but_file_not(app, pair):
    a, b, cid = pair
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
           b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82")
    r = a.client.post(f"/api/conversations/{cid}/messages", data={"file": (io.BytesIO(png), "anh.png")},
                      content_type="multipart/form-data")
    assert r.status_code == 201 and r.get_json()["message"]["kind"] == "image"
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == 0
    r = a.client.post(f"/api/conversations/{cid}/messages", data={"body": SCAM, "file": (io.BytesIO(b"hello"), "ghi chu.txt")},
                      content_type="multipart/form-data")
    assert r.status_code == 201 and r.get_json()["message"]["kind"] == "file"
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["warning"] == 1


# ------------------------------------------------------------------ chan
def test_manual_block_two_way_and_unblock(app, pair):
    a, b, cid = pair
    for _ in range(2):                                                 # 2 lan: chua tu chan
        a.say(cid, SCAM)
    with app.app_context():
        assert Block.query.count() == 0
    assert b.post("/api/blocks", {"user_id": a.id}).status_code == 201     # nguoi bi lua chu dong chan
    r = a.say(cid, OK)
    assert r.status_code == 403 and "không thể nhắn tin" in r.get_json()["error"]
    r = b.say(cid, OK)
    assert r.status_code == 403 and "đã chặn" in r.get_json()["error"]
    cb = b.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert cb["i_blocked"] is True and cb["can_send"] is False and cb["guardian_block"] is None
    ca = a.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert ca["blocked_me"] is True and ca["can_send"] is False and ca["other"]["online"] is False
    assert a.get("/api/users/search?q=bob").get_json()["users"] == []      # nguoi chan an khoi tim kiem cua ho
    assert [u["username"] for u in b.get("/api/blocks").get_json()["blocked"]] == ["alice"]
    assert a.post("/api/friend-requests", {"user_id": b.id}).status_code in (400, 403)
    assert b.post("/api/blocks", {"user_id": a.id}).status_code == 201     # chan lai khong loi
    assert b.delete(f"/api/blocks/{a.id}").status_code == 200              # chan tay: bo chan binh thuong
    assert a.say(cid, OK).status_code == 201
    assert b.post("/api/blocks", {"user_id": b.id}).status_code == 400
    assert len(b.get(f"/api/conversations/{cid}/messages").get_json()["messages"]) == 3


def test_unfriend_then_message_request(pair):
    a, b, cid = pair
    assert a.delete(f"/api/friends/{b.id}").status_code == 200
    assert a.say(cid, OK).status_code == 201                              # thanh nguoi la: van nhan duoc
    cb = b.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert cb["can_send"] is True and cb["is_friend"] is False and cb["request"] is True
    assert b.say(cid, "chào") .status_code == 201                         # tra loi -> ra khoi hop tin nhan cho
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["request"] is False


def test_stranger_message_request_and_apk(app, mk):
    a, s = mk("alice"), mk("stranger")
    cid = s.conv_with(a)
    assert s.say(cid, "Chào chị").status_code == 201
    ca = a.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert ca["request"] is True and ca["is_friend"] is False
    assert s.get(f"/api/conversations/{cid}").get_json()["conversation"]["request"] is False   # nguoi gui khong o hop cho
    r = s.client.post(f"/api/conversations/{cid}/messages", data={"file": (io.BytesIO(b"PK apk"), "XacMinh.apk")},
                      content_type="multipart/form-data")
    assert r.status_code == 201
    att = r.get_json()["message"]["attachment"]
    assert att["is_apk"] and not att["is_image"]
    with app.app_context():
        m = Message.query.order_by(Message.id.desc()).first()
        assert not m.attachment_path.endswith(".apk")                                          # khong luu duoi .apk
    got = a.get(att["url"])
    assert got.status_code == 200 and got.headers["Content-Type"] == "application/octet-stream"
    assert "attachment" in got.headers["Content-Disposition"]


# ------------------------------------------------------------------ dinh kem
def test_attachments_validation_and_access(app, pair, mk):
    a, b, cid = pair
    url = f"/api/conversations/{cid}/messages"
    send = lambda name, data: a.client.post(url, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    assert send("virus.exe", b"MZ").status_code == 400
    assert send("a.svg", b"<svg onload=alert(1)>").status_code == 400
    assert send("rong.txt", b"").status_code == 400
    assert send("lon.zip", b"0" * (10 * 1024 * 1024 + 1)).status_code in (400, 413)
    r = send("Báo cáo tháng.pdf", b"%PDF-1.4 test")
    assert r.status_code == 201
    m = r.get_json()["message"]
    assert m["attachment"]["name"] == "Báo cáo tháng.pdf" and not m["attachment"]["is_image"]
    got = b.get(m["attachment"]["url"])
    assert got.status_code == 200 and got.data == b"%PDF-1.4 test"
    assert "attachment" in got.headers["Content-Disposition"]
    c = mk("carol")
    assert c.get(m["attachment"]["url"]).status_code == 404                # nguoi ngoai khong tai duoc
    assert app.test_client().get(m["attachment"]["url"]).status_code == 401
    assert a.get("/api/attachments/99999").status_code == 404


# ------------------------------------------------------------------ realtime
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


def events(client, name):
    return [e["args"][0] for e in client.get_received() if e["name"] == name]


def test_socket_requires_login(app, sio):
    from services.realtime import socketio
    c = socketio.test_client(app, flask_test_client=app.test_client())
    assert not c.is_connected()


def test_realtime_delivery_and_warning_payloads(pair, sio):
    """Tin den nguoi nhan NGAY (chua co canh bao); Ve si phan tich nen roi day 'guardian:message' CHI cho nguoi nhan.
    Lan 3: tu dong chan -> ca 2 ben nhan 'block:update' + thong bao."""
    a, b, cid = pair
    ca, cb = sio(a), sio(b)
    ca.get_received(); cb.get_received()
    a.say(cid, SCAM)
    rb, ra = cb.get_received(), ca.get_received()
    new_b = [e["args"][0] for e in rb if e["name"] == "message:new"]
    assert new_b[0]["message"]["warning_level"] == 0 and new_b[0]["message"]["scan"] == "pending"
    assert new_b[0]["message"]["delivered_at"]
    g_b = [e["args"][0] for e in rb if e["name"] == "guardian:message"]
    assert g_b and g_b[0]["message"]["warning_level"] == 1 and g_b[0]["conversation"]["warning"] == 1
    assert g_b[0]["message"]["guard"]["explanation"] and g_b[0]["message"]["scan"] == "done"
    assert not [e for e in ra if e["name"] in ("guardian:message", "block:update")]   # nguoi gui khong biet (lan 1-2)
    a.say(cid, SCAM)
    ca.get_received(); cb.get_received()
    a.say(cid, SCAM)
    rb, ra = cb.get_received(), ca.get_received()
    g_b = [e["args"][0] for e in rb if e["name"] == "guardian:message"][0]
    assert g_b["message"]["warning_level"] == 3 and g_b["conversation"]["guardian_block"]["role"] == "protected"
    for got in (ra, rb):                                               # lan 3: ca 2 ben duoc bao
        assert any(e["name"] == "block:update" for e in got)
        assert any(e["name"] == "notify:new" and e["args"][0]["kind"] == "guardian_block" for e in got)


def test_realtime_seen_typing_presence(pair, sio):
    a, b, cid = pair
    ca = sio(a)
    ca.get_received()
    cb = sio(b)
    pres = events(ca, "presence")
    assert pres and pres[-1]["user_id"] == b.id and pres[-1]["online"] is True
    cb.get_received()
    cb.emit("typing", {"conversation_id": cid, "is_typing": True})
    t = events(ca, "typing")
    assert t and t[0]["is_typing"] is True and t[0]["user_id"] == b.id
    cb.emit("typing", {"conversation_id": 99999, "is_typing": True})      # cuoc chat la: bo qua
    cb.emit("typing", "rac")
    assert events(ca, "typing") == []
    a.say(cid, OK)
    ca.get_received()
    b.post(f"/api/conversations/{cid}/read")
    st = events(ca, "message:status")
    assert st and st[0]["status"] == "seen"
    cb.disconnect()
    pres = events(ca, "presence")
    assert pres and pres[-1]["online"] is False


def test_offline_then_delivered_on_connect(pair, sio):
    a, b, cid = pair
    ca = sio(a)
    ca.get_received()
    a.say(cid, OK)
    assert a.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]["delivered_at"] is None
    sio(b)
    st = events(ca, "message:status")
    assert st and st[0]["status"] == "delivered"
    assert a.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]["delivered_at"]


def test_blocked_user_does_not_see_presence_or_typing(pair, sio):
    a, b, cid = pair
    b.post("/api/blocks", {"user_id": a.id})
    ca, cb = sio(a), sio(b)
    ca.get_received(); cb.get_received()
    cb.emit("typing", {"conversation_id": cid, "is_typing": True})
    assert events(ca, "typing") == []
    ca.emit("typing", {"conversation_id": cid, "is_typing": True})
    assert events(cb, "typing") == []


def test_api_unauthenticated(app):
    c = app.test_client()
    for url in ("/api/conversations", "/api/friends", "/api/summary", "/api/blocks"):
        assert c.get(url).status_code == 401, url


def test_migration_tables_exist(app):
    with app.app_context():
        tables = set(db.inspect(db.engine).get_table_names())
    assert {"users", "friend_requests", "blocks", "conversations", "messages", "scam_counters",
            "feed_authors", "feed_posts", "alembic_version"} <= tables


# ------------------------------------------------------------------ moi mo hinh = the gioi tai khoan rieng
def test_accounts_separate_per_model(app, mk):
    from services.ai_client import manager
    a, b = mk("alice"), mk("bob")
    a.befriend(b)
    cid = a.conv_with(b)
    a.say(cid, OK)
    old_uid = a.id
    manager.set_predictor("phobert", FakePredictor())          # quan tri doi sang PhoBERT
    # phien cu bi vo hieu (dang xuat), tai khoan cu khong ton tai trong the gioi moi
    assert a.get("/feed").status_code == 302
    assert a.get("/api/conversations").status_code == 401
    c = app.test_client()
    assert "không đúng" in c.post("/login", data={"username": "alice", "password": "matkhau1"}).get_data(as_text=True)
    # cung ten van dang ky duoc o mo hinh moi (la tai khoan khac)
    a2 = mk("alice")
    assert a2.id != old_uid
    assert a2.get("/api/users/search?q=bob").get_json()["users"] == []      # khong thay nguoi dung mo hinh khac
    assert a2.get("/api/friends").get_json()["friends"] == []
    assert a2.get("/api/conversations").get_json()["conversations"] == []
    # khong the tuong tac cheo bang cach doan id
    assert a2.post("/api/friend-requests", {"user_id": b.id}).status_code == 404
    assert a2.post("/api/blocks", {"user_id": b.id}).status_code == 404
    assert a2.post("/api/conversations", {"user_id": b.id}).status_code == 404
    assert a2.get(f"/api/conversations/{cid}").status_code == 404
    # quay lai SVM: du lieu cu con nguyen
    manager.set_predictor("svm", FakePredictor())
    c = app.test_client()
    assert c.post("/login", data={"username": "alice", "password": "matkhau1"}).status_code == 302
    assert [m["body"] for m in a.get(f"/api/conversations/{cid}/messages").get_json()["messages"]] == [OK]
    with app.app_context():
        assert {(u.model_key, u.username) for u in User.query.all()} == {("svm", "alice"), ("svm", "bob"), ("phobert", "alice")}


def test_model_switch_broadcast_and_real_switch_path(app, mk, sio, monkeypatch):
    import time
    from services import ai_client
    from services.ai_client import manager
    a = mk("alice")
    ca = sio(a)
    ca.get_received()
    monkeypatch.setattr(ai_client, "_build", lambda key, spec: FakePredictor())
    manager.select("viso")
    for _ in range(100):
        if not manager.status()["loading"]:
            break
        time.sleep(0.05)
    assert manager.active == "viso" and manager.status()["error"] is None
    assert any(e["name"] == "system:model_changed" and e["args"][0]["model"] == "viso" for e in ca.get_received())
    manager.set_predictor("svm", FakePredictor())
