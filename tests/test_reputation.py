"""Do uy tin nguoi gui loi moi ket ban: tuoi tai khoan, ban chung, so lan doi ten -> diem 0..100 -> mau.
Nguoi dung CHI thay mau + nhan; diem so + chi tiet CHI quan tri vien thay."""
from datetime import timedelta

from db.database import db, utcnow
from db.models import NameHistory, User


def _age(app, uid, days):
    with app.app_context():
        u = db.session.get(User, uid)
        u.created_at = utcnow() - timedelta(days=days)
        db.session.commit()


def _renames(app, uid, n):
    with app.app_context():
        for i in range(n):
            db.session.add(NameHistory(user_id=uid, old_name=f"Ten {i}", new_name=f"Ten {i + 1}"))
        db.session.commit()


def _eval(app, target_id, viewer_id):
    from services.reputation_service import evaluate
    with app.app_context():
        return evaluate(db.session.get(User, target_id), viewer_id)


def _points(rep):
    return {i["key"]: i["points"] for i in rep["items"]}


def test_score_rules_and_levels(app, mk):
    a, b = mk("alice"), mk("bob")
    # tai khoan vua tao (< 1 ngay), 0 ban chung, chua doi ten: 70 - 25 - 10 + 5 = 40 -> do
    rep = _eval(app, b.id, a.id)
    assert _points(rep) == {"age": -25, "mutual": -10, "renames": 5} and rep["score"] == 40 and rep["level"] == "red"
    # 10 ngay (-5), 1 ban chung (0), doi ten 1 lan (0): 65 -> vang
    c = mk("carol")
    a.befriend(c)
    b.befriend(c)
    _age(app, b.id, 10)
    _renames(app, b.id, 1)
    rep = _eval(app, b.id, a.id)
    assert _points(rep) == {"age": -5, "mutual": 0, "renames": 0} and rep["score"] == 65 and rep["level"] == "yellow"
    # > 1 nam (+20), 3 ban chung (+10): 70 + 20 + 10 + 0 = 100 -> xanh (kep toi da 100)
    for name in ("dan", "eve"):
        x = mk(name)
        a.befriend(x)
        b.befriend(x)
    _age(app, b.id, 400)
    rep = _eval(app, b.id, a.id)
    assert _points(rep)["mutual"] == 10 and rep["score"] == 100 and rep["level"] == "green"
    # doi ten nhieu lan (tong 6 lan -> -25): 70 + 20 + 10 - 25 = 75 -> vang
    _renames(app, b.id, 5)
    rep = _eval(app, b.id, a.id)
    assert _points(rep)["renames"] == -25 and rep["score"] == 75 and rep["level"] == "yellow"


def test_age_and_mutual_boundaries(app):
    from services.reputation_service import _step, level_of
    with app.app_context():
        cfg = app.config
        steps = cfg["REPUTATION_AGE_STEPS"]
        assert [_step(d, steps, strict=True) for d in (0, 0.9, 1, 6.9, 7, 29, 30, 179, 180, 364, 365, 3000)] == \
               [-25, -25, -15, -15, -5, -5, 5, 5, 10, 10, 20, 20]
        assert [_step(n, cfg["REPUTATION_MUTUAL_STEPS"]) for n in (0, 1, 2, 3, 5, 6, 10, 11)] == [-10, 0, 0, 10, 10, 15, 15, 20]
        assert [_step(n, cfg["REPUTATION_RENAME_STEPS"]) for n in (0, 1, 2, 3, 4, 5, 9)] == [5, 0, -5, -15, -15, -25, -25]
        assert (level_of(100), level_of(80), level_of(79), level_of(50), level_of(49), level_of(0)) == \
               ("green", "green", "yellow", "yellow", "red", "red")


def test_users_only_see_color_not_score(app, mk):
    a, b = mk("alice"), mk("bob")
    assert b.post("/api/friend-requests", {"user_id": a.id}).status_code == 201
    inc = a.get("/api/friend-requests").get_json()["incoming"]
    rep = inc[0]["reputation"]
    assert rep["level"] == "red" and rep["label"] == "Cảnh giác" and set(rep) == {"level", "label", "hint"}   # khong co diem
    # trang ho so nguoi khac: co huy hieu, khong co diem; ho so cua chinh minh: khong co
    html = a.get("/u/bob").get_data(as_text=True)
    assert "rep-badge rep-red" in html and "Cảnh giác" in html and '"score"' not in html
    assert "rep-badge" not in a.get("/u/alice").get_data(as_text=True)
    # chat voi nguoi la: co huy hieu; da la ban be: khong
    cid = b.conv_with(a)
    conv = a.get(f"/api/conversations/{cid}").get_json()["conversation"]
    assert conv["reputation"]["level"] == "red" and "score" not in conv["reputation"]
    rid = inc[0]["id"]
    assert a.post(f"/api/friend-requests/{rid}/accept").status_code == 200
    assert a.get(f"/api/conversations/{cid}").get_json()["conversation"]["reputation"] is None


def test_admin_sees_score_and_breakdown(app, mk):
    a, b = mk("alice"), mk("bob")
    b.post("/api/friend-requests", {"user_id": a.id})
    c = app.test_client()
    assert c.get(f"/api/admin/reputation/{b.id}?viewer={a.id}").status_code == 403
    a_client = a.client
    assert a_client.get(f"/api/admin/reputation/{b.id}?viewer={a.id}").status_code == 403         # nguoi dung thuong
    c.post("/admin", data={"password": app.config["ADMIN_PASSWORD"]})
    rep = c.get(f"/api/admin/reputation/{b.id}?viewer={a.id}").get_json()["reputation"]
    assert rep["score"] == 40 and rep["level"] == "red" and len(rep["items"]) == 3
    html = c.get("/admin?tab=reputation").get_data(as_text=True)
    assert "@bob" in html and ">40<" in html and "Không có bạn chung" in html and "-25" in html


def test_reputation_independent_of_guardian(app, pair):
    """Do uy tin KHONG anh huong toi AI 3 / luat 3 lan: tin an toan tu tai khoan do van muc 0."""
    a, b, cid = pair
    m = a.say(cid, "Chiều nay đi ăn cơm không?").get_json()["message"]
    got = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m["id"] == got["id"] and got["warning_level"] == 0
