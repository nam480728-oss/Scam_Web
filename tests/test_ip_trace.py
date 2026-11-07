"""Truy vet IP: luu IP khi gui tin / dang nhap, ho so truy vet khi Ve si tu dong chan (lan 3), chi quan tri vien xem,
nan nhan gui yeu cau -> quan tri vien duyet / tu choi, xuat CSV, tu xoa IP cu."""
from datetime import timedelta

from db.database import db, utcnow
from db.models import LoginLog, Message, ScamTrace, TraceRequest

SCAM = "Bấm link này để nhận trúng thưởng nhé"
UA = {"User-Agent": "TestBrowser/1.0"}


def _block(a, b, cid):
    for i in range(3):
        assert a.say(cid, SCAM + str(i)).status_code == 201


def _admin(app):
    c = app.test_client()
    assert c.post("/admin", data={"password": app.config["ADMIN_PASSWORD"]}).status_code == 302
    return c


def test_ip_saved_on_message_and_login_but_hidden_from_users(app, mk):
    a, b = mk("alice"), mk("bob")
    a.befriend(b)
    cid = a.conv_with(b)
    r = a.client.post(f"/api/conversations/{cid}/messages", json={"body": "Chào bạn"}, headers=UA,
                      environ_base={"REMOTE_ADDR": "198.51.100.77"})
    assert r.status_code == 201
    with app.app_context():
        m = Message.query.one()
        assert m.sender_ip == "198.51.100.77" and m.sender_user_agent == "TestBrowser/1.0"
        assert LoginLog.query.filter_by(user_id=a.id).count() == 1           # dang ky = dang nhap lan dau
    for who in (a, b):                                                       # khong ai thay IP qua API nguoi dung
        body = who.get(f"/api/conversations/{cid}/messages").get_data(as_text=True)
        assert "198.51.100.77" not in body and "sender_ip" not in body
    c = app.test_client()
    assert c.post("/login", data={"username": "alice", "password": "matkhau1"},
                  environ_base={"REMOTE_ADDR": "203.0.113.5"}).status_code == 302
    with app.app_context():
        assert LoginLog.query.filter_by(user_id=a.id).order_by(LoginLog.id.desc()).first().ip == "203.0.113.5"


def test_x_forwarded_for_ignored_without_trust_proxy(app, pair):
    a, b, cid = pair
    a.client.post(f"/api/conversations/{cid}/messages", json={"body": "hi"}, headers={"X-Forwarded-For": "8.8.8.8"})
    with app.app_context():
        assert Message.query.one().sender_ip == "127.0.0.1"


def test_trace_created_only_on_auto_block(app, pair):
    a, b, cid = pair
    for i in range(2):
        a.say(cid, SCAM + str(i))
    with app.app_context():
        assert ScamTrace.query.count() == 0                                  # lan 1, lan 2: chua tao ho so
    a.say(cid, SCAM + "2")
    with app.app_context():
        t = ScamTrace.query.one()
        assert (t.offender_id, t.victim_id, t.conversation_id, t.block_nth) == (a.id, b.id, cid, 1)
        assert t.ip == "127.0.0.1" and t.geo_source == "private" and t.offender_username == "alice"
        assert len(t.evidence["messages"]) == 3 and t.evidence["ips"][0]["place"] == "Mạng nội bộ / localhost"
        assert t.evidence["logins"] and t.evidence["logins"][0]["ip"] == "127.0.0.1"


def test_geolocate_sources(app, monkeypatch):
    from services import ip_geo
    with app.test_request_context():
        g = ip_geo.geolocate("203.0.113.24")                                 # IP demo trong scenarios.json
        assert g["source"] == "demo" and g["region"] == "TP. Hồ Chí Minh"
        assert ip_geo.geolocate("192.168.1.9")["source"] == "private"
        assert ip_geo.geolocate("8.8.8.8")["source"] == "unknown"            # mac dinh: khong mmdb, khong goi mang
        assert ip_geo.geolocate(None)["source"] == "unknown" and ip_geo.geolocate("khong-phai-ip")["source"] == "unknown"

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"status": "success", "country": "Vietnam", "regionName": "Hanoi", "city": "Hanoi", "isp": "VNPT"}
        calls = []
        import requests
        monkeypatch.setattr(requests, "get", lambda url, timeout: calls.append((url, timeout)) or Resp())
        app.config["GEOIP_ONLINE"] = True
        try:
            g = ip_geo.geolocate("8.8.8.8")
            assert g == {"country": "Vietnam", "region": "Hanoi", "city": "Hanoi", "isp": "VNPT", "source": "online"}
            assert "8.8.8.8" in calls[0][0] and calls[0][1] == app.config["GEOIP_TIMEOUT"]
            monkeypatch.setattr(requests, "get", lambda url, timeout: (_ for _ in ()).throw(TimeoutError()))
            assert ip_geo.geolocate("8.8.4.4")["source"] == "unknown"      # loi mang: khong nem loi
        finally:
            app.config["GEOIP_ONLINE"] = False
        assert ip_geo.place({"city": "Hanoi", "region": "Hanoi", "country": "Vietnam"}) == "Hanoi, Vietnam"


def test_trace_request_flow_approve(app, pair, mk):
    a, b, cid = pair
    _block(a, b, cid)
    other = mk("carol")
    # chi nan nhan (ben duoc bao ve) moi thay nut + gui duoc
    cb = b.get(f"/api/conversations/{cid}").get_json()["conversation"]
    ca = a.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert cb["guardian_block"]["trace"]["status"] is None and ca["guardian_block"]["trace"] is None
    assert b.get("/api/blocks").get_json()["blocked"][0]["trace"]["trace_id"]
    assert a.post("/api/trace-requests", {"user_id": b.id, "reason": "toi muon biet IP cua nguoi nay"}).status_code == 404
    assert other.post("/api/trace-requests", {"user_id": a.id, "reason": "toi muon biet IP cua nguoi nay"}).status_code == 404
    assert b.post("/api/trace-requests", {"user_id": a.id, "reason": "ngan"}).status_code == 400
    r = b.post("/api/trace-requests", {"user_id": a.id, "reason": "Tôi bị lừa chuyển tiền, cần nộp cho công an"})
    assert r.status_code == 201 and r.get_json()["request"]["status"] == "pending" and "trace" not in r.get_json()["request"]
    assert b.post("/api/trace-requests", {"user_id": a.id, "reason": "Gửi lại lần nữa cho chắc ăn"}).status_code == 409
    mine = b.get("/api/trace-requests").get_json()["requests"]
    assert len(mine) == 1 and "trace" not in mine[0]                        # chua duyet: khong thay IP
    assert "127.0.0.1" not in b.get("/trace-requests").get_data(as_text=True)
    # nguoi dung thuong khong duyet duoc
    rid = mine[0]["id"]
    assert b.post(f"/api/admin/trace-requests/{rid}", {"action": "approve"}).status_code == 403
    adm = _admin(app)
    html = adm.get("/admin?tab=requests").get_data(as_text=True)
    assert "Tôi bị lừa chuyển tiền" in html and "127.0.0.1" in html
    assert adm.post(f"/admin/trace-requests/{rid}", data={"action": "approve", "note": "Đã chuyển hồ sơ"}).status_code == 302
    assert adm.post(f"/api/admin/trace-requests/{rid}", json={"action": "reject"}).status_code == 409   # da xu ly
    mine = b.get("/api/trace-requests").get_json()["requests"]
    assert mine[0]["status"] == "approved" and mine[0]["trace"]["ip"] == "127.0.0.1"
    assert "user_agent" not in mine[0]["trace"] and mine[0]["admin_note"] == "Đã chuyển hồ sơ"
    page = b.get("/trace-requests").get_data(as_text=True)
    assert "127.0.0.1" in page and "Mạng nội bộ" in page
    notes = b.get("/api/notifications").get_json()["notifications"]
    assert any(n["kind"] == "trace" and n["link"] == "/trace-requests" for n in notes)
    assert b.get(f"/api/conversations/{cid}").get_json()["conversation"]["guardian_block"]["trace"]["status"] == "approved"
    assert b.post("/api/trace-requests", {"user_id": a.id, "reason": "Gửi lại lần nữa cho chắc ăn"}).status_code == 409


def test_trace_request_reject_then_resend(app, pair):
    a, b, cid = pair
    _block(a, b, cid)
    b.post("/api/trace-requests", {"user_id": a.id, "reason": "Tôi muốn biết vị trí người này"})
    adm = _admin(app)
    rid = adm.get("/api/admin/trace-requests?status=pending").get_json()["requests"][0]["id"]
    r = adm.post(f"/api/admin/trace-requests/{rid}", json={"action": "reject", "note": "Chưa đủ căn cứ"})
    assert r.status_code == 200 and r.get_json()["request"]["status"] == "rejected"
    mine = b.get("/api/trace-requests").get_json()["requests"]
    assert mine[0]["status"] == "rejected" and "trace" not in mine[0] and mine[0]["admin_note"] == "Chưa đủ căn cứ"
    assert b.post("/api/trace-requests", {"user_id": a.id, "reason": "Bổ sung: tôi đã mất 5 triệu"}).status_code == 201
    with app.app_context():
        assert TraceRequest.query.count() == 2


def test_admin_traces_page_filter_and_csv(app, pair):
    a, b, cid = pair
    _block(a, b, cid)
    c = app.test_client()
    assert c.get("/admin/traces.csv").status_code == 302 and c.get("/api/admin/traces").status_code == 403
    assert b.get("/api/admin/traces").status_code == 403
    adm = _admin(app)
    traces = adm.get("/api/admin/traces").get_json()["traces"]
    assert len(traces) == 1 and traces[0]["ip"] == "127.0.0.1" and traces[0]["offender"]["username"] == "alice"
    assert adm.get("/api/admin/traces?q=khongco").get_json()["traces"] == []
    assert len(adm.get("/api/admin/traces?q=127.0").get_json()["traces"]) == 1
    html = adm.get("/admin?tab=traces").get_data(as_text=True)
    assert "@alice" in html and "127.0.0.1" in html and "Mạng nội bộ" in html
    r = adm.get("/admin/traces.csv")
    text = r.get_data(as_text=True)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert text.startswith("﻿") and "ke_gui" in text and "alice" in text and "127.0.0.1" in text


def test_purge_keeps_traces(app, pair):
    from services import trace_service
    a, b, cid = pair
    _block(a, b, cid)
    with app.app_context():
        old = utcnow() - timedelta(days=app.config["IP_RETENTION_DAYS"] + 1)
        Message.query.update({Message.created_at: old})
        LoginLog.query.update({LoginLog.created_at: old})
        db.session.commit()
        assert trace_service.purge_expired(force=True) > 0
        assert Message.query.filter(Message.sender_ip.isnot(None)).count() == 0
        assert LoginLog.query.count() == 0
        assert ScamTrace.query.one().ip == "127.0.0.1"                     # ho so truy vet giu lau dai


def test_demo_seed_ip_and_name_history(app):
    from services import demo_service as ds
    with app.app_context():
        spec = ds.load()["actors"]["nguyenthuha.2025"]
        u = ds.ensure_user("svm", "nguyenthuha.2025", spec["name"], days=spec["days"], old_names=spec["old_names"],
                           demo_ip=spec["demo_ip"])
        victim = ds.ensure_user("svm", "balan", "Trần Thị Lan", days=1200)
        db.session.commit()
        from db.models import NameHistory
        chain = [(h.old_name, h.new_name) for h in NameHistory.query.filter_by(user_id=u.id).order_by(NameHistory.id)]
        assert chain == [("Hà Nguyễn", "Thu Hà Official"), ("Thu Hà Official", "Nguyễn Thu Hà")]
        assert LoginLog.query.filter_by(user_id=u.id).one().ip == "203.0.113.24"
        m = ds.send(u, victim, "chào bà", process=False)
        assert m.sender_ip == "203.0.113.24"
        from services.reputation_service import evaluate
        rep = evaluate(u, victim.id)                                         # 1 ngay, 0 ban chung, doi ten 2 lan
        assert rep["score"] == 70 - 15 - 10 - 5 and rep["level"] == "red"
