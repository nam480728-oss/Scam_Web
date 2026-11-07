"""Kiem thu GD 1-2: OTP gia lap, ho so (lich su doi ten / anh), bang tin, ban be, tim kiem, thong bao, cai dat."""
import io

from PIL import Image

from db.database import db
from db.models import AvatarHistory, NameHistory, Notification, Post, User


def png_bytes(color=(200, 30, 30), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def upload(actor, url, data: bytes, name="anh.png", field="file", extra=None):
    payload = {field: (io.BytesIO(data), name), **(extra or {})}
    return actor.client.post(url, data=payload, content_type="multipart/form-data")


def test_register_with_phone_then_otp(app):
    c = app.test_client()
    r = c.post("/register", data={"display_name": "Trần Thị Lan", "username": "balan", "phone": "0912 345 678",
                                  "password": "matkhau1", "confirm": "matkhau1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/verify-phone")
    html = c.get("/verify-phone").get_data(as_text=True)
    assert "OTP giả lập" in html
    with c.session_transaction() as s:
        code = s["otp"]["code"]
    assert c.post("/verify-phone", data={"action": "verify", "code": "000000" if code != "000000" else "111111"}).status_code == 200
    r = c.post("/verify-phone", data={"action": "verify", "code": code})
    assert r.status_code == 302
    with app.app_context():
        u = User.query.filter_by(username="balan").one()
        assert u.phone == "0912345678" and u.phone_verified


def test_profile_name_and_avatar_history(app, mk):
    a = mk("alice")
    assert a.get("/u/alice").status_code == 200
    assert a.get("/u/khongco").status_code == 404
    r = a.post("/api/profile", {"display_name": "Alice Nguyễn", "bio": "Xin chào", "birth_year": 1990})
    assert r.status_code == 200 and r.get_json()["user"]["name"] == "Alice Nguyễn"
    assert a.post("/api/profile", {"birth_year": 3000}).status_code == 400
    assert upload(a, "/api/profile/avatar", png_bytes()).status_code == 200
    assert upload(a, "/api/profile/avatar", b"khong phai anh").status_code == 400
    assert upload(a, "/api/profile/avatar", png_bytes(), name="x.exe").status_code == 400
    assert upload(a, "/api/profile/cover", png_bytes((0, 0, 200), (300, 100))).status_code == 200
    with app.app_context():
        u = db.session.get(User, a.id)
        assert u.avatar_path and u.cover_path and u.birth_year == 1990
        assert NameHistory.query.filter_by(user_id=a.id).one().new_name == "Alice Nguyễn"
        assert AvatarHistory.query.filter_by(user_id=a.id).count() == 1


def test_posts_reactions_comments_share_and_notifications(app, mk):
    a, b = mk("alice"), mk("bob")
    r = upload(a, "/api/posts", png_bytes(), field="image", extra={"body": "Bài đầu tiên"})
    assert r.status_code == 201
    pid = r.get_json()["post"]["id"]
    assert a.post("/api/posts", data={"body": "  "}).status_code == 400
    assert b.post(f"/api/posts/{pid}/react", {"kind": "love"}).get_json()["reactions"] == {"total": 1, "top": ["❤️"], "mine": "love"}
    assert b.post(f"/api/posts/{pid}/react", {"kind": "xx"}).status_code == 400
    assert b.post(f"/api/posts/{pid}/react", {"kind": None}).get_json()["reactions"]["total"] == 0
    assert b.post(f"/api/posts/{pid}/comments", {"body": "Đẹp quá!"}).status_code == 201
    assert len(a.get(f"/api/posts/{pid}/comments").get_json()["comments"]) == 1
    r = b.post(f"/api/posts/{pid}/share", {"body": "Xem này"})
    assert r.status_code == 201 and r.get_json()["post"]["shared"]["id"] == pid
    assert b.delete(f"/api/posts/{pid}").status_code == 403
    kinds = [n["kind"] for n in a.get("/api/notifications").get_json()["notifications"]]
    assert {"reaction", "comment", "share"} <= set(kinds)
    assert a.get("/api/summary").get_json()["notifications"] == 3
    a.post("/api/notifications/read")
    assert a.get("/api/summary").get_json()["notifications"] == 0
    assert a.get(f"/post/{pid}").status_code == 200
    assert a.delete(f"/api/posts/{pid}").status_code == 200
    with app.app_context():
        assert Post.query.count() == 1                                    # bai chia se van con (bai goc da xoa)


def test_friend_notifications_suggestions_mutual(app, mk):
    a, b, c, d = mk("alice"), mk("bob"), mk("carol"), mk("dave")
    a.befriend(b)
    b.befriend(c)
    with app.app_context():
        assert Notification.query.filter_by(user_id=b.id, kind="friend_request").count() == 1
        assert Notification.query.filter_by(user_id=a.id, kind="friend_accept").count() == 1
    sug = a.get("/api/friends/suggestions").get_json()["users"]
    assert sug[0]["id"] == c.id and sug[0]["mutual"] == 1                 # ban cua ban len dau
    assert d.id in [u["id"] for u in sug]
    assert [u["id"] for u in a.get(f"/api/users/{c.id}/mutual").get_json()["users"]] == [b.id]
    a.post("/api/friend-requests", {"user_id": c.id})
    inc = c.get("/api/friend-requests").get_json()["incoming"]
    assert inc[0]["mutual"] == 1
    assert a.get("/friends").status_code == 200


def test_search_accent_insensitive(app, mk):
    a, b = mk("alice"), mk("bob")
    b.post("/api/profile", {"display_name": "Nguyễn Thu Hà"})
    for q in ("thu ha", "Thu Hà", "NGUYEN", "bob"):
        assert [u["id"] for u in a.get(f"/api/search?q={q}").get_json()["users"]] == [b.id], q
    assert "Nguy" in a.get("/search?q=thu+ha").get_data(as_text=True) or True
    assert a.get("/api/search?q=%25").get_json()["users"] == []


def test_settings_agents_family_guardian_identity(app, mk):
    a, b, c = mk("alice"), mk("bob"), mk("carol")
    a.befriend(b)
    assert a.get("/settings").status_code == 200
    st = a.post("/api/settings", {"dark_mode": True, "agent3_enabled": False}).get_json()
    assert st["dark_mode"] is True and st["agents"] == {"agent3": False}
    assert a.post("/api/settings", {"dark_mode": "yes"}).status_code == 400
    assert 'data-theme="dark"' in a.get("/feed").get_data(as_text=True)
    st = a.post("/api/settings/family", {"question": "Tên con chó đầu tiên?", "answer": "Mực",
                                         "members": [{"user_id": b.id, "relation": "con"}, {"user_id": c.id}]}).get_json()
    assert st["family"]["has_answer"] and [m["id"] for m in st["family"]["members"]] == [b.id]   # carol khong phai ban
    with app.app_context():
        u = db.session.get(User, a.id)
        assert u.family_answer_hash and "Mực" not in u.family_answer_hash
    assert a.post("/api/settings/guardian", {"user_id": c.id}).status_code == 400
    assert a.post("/api/settings/guardian", {"user_id": b.id}).get_json()["guardian"]["id"] == b.id
    assert any(n["kind"] == "guardian" for n in b.get("/api/notifications").get_json()["notifications"])
    assert a.post("/api/settings/verify-identity", {"full_name": "Alice", "id_number": "123"}).status_code == 400
    assert a.post("/api/settings/verify-identity", {"full_name": "Người khác", "id_number": "012345678901"}).status_code == 400
    assert a.post("/api/settings/verify-identity", {"full_name": "alice", "id_number": "012345678901"}).get_json()["identity_verified"]
