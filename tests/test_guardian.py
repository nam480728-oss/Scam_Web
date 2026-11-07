"""Kiem thu Ve si chi con AI 3: tien xu ly van ban, adapter AI 3 (schema, du phong, hieu chinh ngu canh), bo quyet dinh
luat 3 lan, luong tin nhan qua API, bao cao = nhan train, Hoi Ve si, bang dieu khien."""
import pytest

from agents.agent3_adapter import Reader
from agents.agent3_text import analyze_text, normalize
from agents.contracts import Agent3Result
from agents.decision import decide
from db.models import Block, Feedback, GuardianEvent, Notification, Report


# =========================================================================== tien xu ly
@pytest.mark.parametrize("raw, expected", [
    ("V.i.ệ.c n.h.ẹ lương cao", "việc nhẹ lương cao"),
    ("c.h.u.y.ể.n gấp vào stk", "chuyển gấp vào số tài khoản"),
    ("ck t 200k nhé", "chuyển khoản tớ 200k nhé"),
    ("ko bik ib zl đi", "không biết nhắn tin zalo đi"),
    ("C-H-U-Y-E-N T-I-E-N", "chuyen tien"),
])
def test_normalize_teencode_and_split_letters(raw, expected):
    assert normalize(raw).normalized == expected


def test_normalize_keeps_links_and_folds():
    r = normalize("Xem t.me/abcd và Việc Nhẹ")
    assert "t.me/abcd" in r.normalized and r.folded.endswith("viec nhe")


def test_analyze_text_accounts_urls_amounts_keywords():
    t = analyze_text("Mẹ chuyển giúp con 15 triệu vào stk 9999 0001 234567 Vietcombank, "
                     "xem https://evn-thanhtoan.xyz/pay và www.youtube.com/watch?v=1. Giá 3.5 triệu")
    assert t["bank_accounts"] == ["99990001234567"]
    assert [u["domain"] for u in t["urls"]] == ["evn-thanhtoan.xyz", "youtube.com"]
    assert 15_000_000 in t["amounts"] and 3_500_000 in t["amounts"]
    assert {"money_request"} <= set(t["keywords"])
    assert analyze_text("Mã đơn 123456789 đã giao")["bank_accounts"] == []          # day so khong gan tu "stk/tai khoan"
    assert analyze_text("V.i.ệ.c n.h.ẹ")["changes"]


# =========================================================================== bo quyet dinh: CHI dua vao AI 3
def test_decision_three_strikes_only_ai3():
    calm = Agent3Result(risk_score=0.1)
    assert decide(calm).level == 0 and not decide(calm).flagged
    assert not decide(Agent3Result(risk_score=0.45)).flagged                       # duoi nguong, khong is_scam
    for a3 in (Agent3Result(risk_score=0.7), Agent3Result(risk_score=0.5, is_scam=True)):
        d = decide(a3, {"urls": [{"url": "x.xyz", "domain": "x.xyz"}]})
        assert d.flagged and d.level == 1 and not d.actions["mask"] and d.actions["blur_links"] and not d.actions["block_sender"]
    scam = Agent3Result(risk_score=0.9, is_scam=True)
    d1 = decide(scam, {}, has_apk=True)
    assert d1.level == 1 and d1.actions["confirm_apk"] and not d1.actions["block_apk"] and d1.rule_level == 3
    d2 = decide(scam, {}, has_apk=True, counter_before=1)
    assert d2.level == 2 and d2.actions["mask"] and d2.actions["block_apk"] and d2.actions["copy_delay"] == 60
    d3 = decide(scam, {}, counter_before=2)
    assert d3.level == 3 and d3.actions["block_sender"]
    d = decide(Agent3Result(risk_score=0.5, is_scam=True, scenario="gia_nguoi_than"), counter_before=5)
    assert d.level == 3 and d.counter_level == 6 and d.actions["family_hint"]       # toi da muc 3


# =========================================================================== adapter AI 3
def test_agent3_payload_schema_validation_and_fallback():
    r = Reader(backend="python", module="khong_ton_tai.module:analyze")
    text = analyze_text("Mẹ chuyển con 15 triệu vào stk 99990001234567 nhé, gấp lắm, đừng nói với bố")
    p = r.build_payload([{"role": "sender", "text": "Mẹ chuyển con 15 triệu vào stk 99990001234567 nhé, gấp lắm, đừng nói với bố",
                          "timestamp": None, "attachments": []}], text, is_friend=False)
    assert set(p) == {"conversation", "context", "text"} and p["context"] == {"is_friend": False}
    res = r.analyze(p)                                               # module khong ton tai -> tu roi ve mock
    assert res.backend == "mock" and res.fallback_reason and res.scenario == "gia_nguoi_than" and res.is_scam
    out = Reader(backend="mock").map_response({"risk_score": "abc", "phase": "khong_hop_le", "signals": "x"}, p)
    assert 0 <= out.risk_score <= 1 and out.phase in ("tiep_can", "tao_tin", "gay_ap_luc", "co_lap", "yeu_cau", "none")
    good = Reader(backend="mock").map_response({"is_scam": True, "risk_score": 0.93, "phase": "yeu_cau", "scenario": "gia_cong_an",
                                                "explanation_vi": "Giả công an"}, p)
    assert good.is_scam and good.scenario == "gia_cong_an" and good.explanation_vi == "Giả công an"
    with pytest.raises(ValueError):
        Reader(backend="mock").map_response(["khong phai dict"], p)


def test_agent3_local_context_calibration():
    """Mo hinh SMS cham sai tin chat binh thuong (vd 'Shop gui STK' ~1.0): ban be + khong ap luc -> giam manh."""
    from services.ai_client import manager

    class Always:
        def predict(self, t):
            return 1.0, True

        def close(self):
            pass
    old = manager._predictor, manager.active
    manager.set_predictor("svm", Always())
    try:
        r = Reader(backend="local")
        msg = "Shop gửi chị STK nhé 0123456789"
        friend = r.analyze(r.build_payload([{"role": "sender", "text": msg}], analyze_text(msg), is_friend=True))
        assert friend.model_prob == 1.0 and friend.risk_score < 0.35 and friend.calibration["factor"] == 0.25
        stranger = r.analyze(r.build_payload([{"role": "sender", "text": msg}], analyze_text(msg), is_friend=False))
        assert stranger.calibration["factor"] == 0.7 and stranger.risk_score >= 0.6
        urgent = "khẩn cấp, chuyển ngay"
        u = r.analyze(r.build_payload([{"role": "sender", "text": urgent}], analyze_text(urgent), is_friend=True))
        assert u.risk_score >= 0.85 and u.calibration["factor"] == 1.0          # ban be nhung gay ap luc: khong giam
    finally:
        manager._predictor, manager.active = old


# =========================================================================== luong day du qua API
SCAM = "Chuyển khoản gấp vào stk 99990008889990, khẩn cấp lắm"


def test_message_pipeline_three_strikes_auto_block(app, mk):
    s = mk("scammer")
    v, other = mk("nan_nhan"), mk("nguoi_khac")
    cid, cid2 = s.conv_with(v), s.conv_with(other)
    assert s.say(cid, "Chào bạn, mình làm quen nhé").status_code == 201
    assert s.say(cid2, "Chào bạn").status_code == 201
    first = v.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert first["warning_level"] == 0
    s.say(cid, SCAM)
    m = v.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m["warning_level"] == 1 and not m["guard"]["mask"] and m["guard"]["explanation"] and m["guard"]["accounts"] == ["99990008889990"]
    s.say(cid, SCAM + " nhé")
    assert v.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]["guard"]["mask"] is True
    s.say(cid, SCAM + " đi")
    m3 = v.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m3["warning_level"] == 3
    with app.app_context():
        assert Block.query.filter_by(blocker_id=v.id, blocked_id=s.id, source="guardian").count() == 1
        assert {n.user_id for n in Notification.query.filter_by(kind="guardian_block")} == {v.id, s.id}   # bao 2 ben
        assert Notification.query.filter_by(user_id=other.id).count() == 0     # KHONG con mien dich bay dan
        assert Report.query.count() == 0                                       # tu chan khong tu bao cao
        ev = GuardianEvent.query.filter_by(message_id=m3["id"]).one()
        assert ev.level == 3 and set(ev.results) == {"text", "agent3", "decision"} and ev.timings["total"] >= 0
    assert s.say(cid, "còn đó không").status_code == 403
    mine = s.get(f"/api/conversations/{cid2}/messages").get_json()["messages"][-1]
    assert mine["warning_level"] == 0 and "guard" not in mine
    why = v.get(f"/api/guardian/messages/{m['id']}").get_json()["event"]
    assert why["results"]["agent3"]["explanation_vi"] and why["results"]["text"]["normalized_text"]
    assert s.get(f"/api/guardian/messages/{m['id']}").status_code == 404        # nguoi gui khong xem duoc


def test_report_is_saved_as_training_label(app, pair, mk):
    a, b, cid = pair
    a.say(cid, SCAM)
    m = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    r = b.post("/api/guardian/report", {"message_id": m["id"]})
    assert r.status_code == 200 and r.get_json()["saved"] is True
    with app.app_context():
        fb = Feedback.query.filter_by(message_id=m["id"]).one()
        assert fb.label == "scam" and fb.text == SCAM and fb.target_user_id == a.id
        assert Report.query.filter_by(reported_id=a.id).count() == 1
        assert Notification.query.filter(Notification.user_id != b.id, Notification.user_id != a.id).count() == 0
    assert b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]["guard"]["feedback"] == "scam"
    assert b.post("/api/guardian/feedback", {"message_id": 999999, "label": "not_scam"}).status_code == 404
    assert a.post("/api/guardian/report", {"message_id": m["id"]}).status_code == 404   # khong tu bao cao tin cua minh


def test_agent3_toggle_off_and_feedback(app, pair):
    a, b, cid = pair
    b.post("/api/settings", {"agent3_enabled": False})
    a.say(cid, "Bấm link này để nhận trúng thưởng nhé")
    m = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m["warning_level"] == 0 and m["scan"] == "off"
    b.post("/api/settings", {"agent3_enabled": True})
    a.say(cid, "Bấm link này để nhận trúng thưởng nhé")
    m = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m["warning_level"] >= 1
    assert b.post("/api/guardian/feedback", {"message_id": m["id"], "label": "not_scam"}).status_code == 200
    m = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"][-1]
    assert m["guard"]["feedback"] == "not_scam"


def test_ask_guardian(pair):
    a, b, cid = pair
    r = a.post("/api/guardian/ask", {"text": "Công an quận thông báo anh liên quan đường dây rửa tiền, phải cài ứng dụng "
                                             "xác minh công dân và chuyển khoản ngay, khẩn cấp"}).get_json()
    assert r["level"] >= 2 and r["verdict"] and r["answer"] and r["advice"] and r["scenario"] == "Giả danh công an"
    assert a.post("/api/guardian/ask", {"text": ""}).get_json()["level"] == 0
    assert a.post("/api/guardian/ask", {"conversation_id": cid}).get_json()["level"] == 0      # chua co tin cua ban
    b.say(cid, "Chiều đi cà phê không?")
    r = a.post("/api/guardian/ask", {"conversation_id": cid}).get_json()
    assert r["level"] <= 1 and "trust" not in r


def test_dashboard_api(app, pair):
    a, b, cid = pair
    a.say(cid, "Chào bạn")
    a.say(cid, "Bấm link này để nhận trúng thưởng nhé")
    ev = b.get("/api/guardian/events").get_json()["events"]
    assert ev and ev[0]["kind"] == "message" and "timings" in ev[0] and "modes" in ev[0]
    st = b.get("/api/guardian/stats").get_json()
    assert st["messages"] == 2 and st["flagged"] == 1 and len(st["hourly"]) == 24
    assert {"auto_blocks", "appeals", "labels", "agent3_avg_ms"} <= set(st)
    assert b.get("/guardian").status_code == 200 and b.get("/demo").status_code == 200
    assert b.get("/api/guardian/trust/1").status_code == 404                      # The tin nhiem da bo
