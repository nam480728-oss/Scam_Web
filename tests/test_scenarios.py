"""Kiem thu seed + 8 kich ban demo (chi tin nhan) chay qua day chuyen that (AI 3 gia lap)."""
import pytest

from db.models import Block, Feedback, GuardianEvent, Message, Notification, Report, User
from services import demo_service as ds


@pytest.fixture
def world(app):
    app.config["GUARDIAN_ASYNC"] = False
    with app.app_context():
        import seed
        seed.seed_world("svm", reset=False, scan=False)
        yield "svm"


def run(world, sid):
    return [ds.run_step(world, step) for step in ds.scenario(sid)["steps"]]


def victim_levels(world, sid):
    v = ds.resolve(world, ds.scenario(sid)["victim"])
    return [m.warning_level for m in Message.query.join(Message.conversation)
            .filter(Message.sender_id != v.id, Message.kind != "call").all() if m.conversation.has_user(v.id)]


def test_seed_world(world):
    assert User.query.filter_by(model_key=world).count() >= 30
    lan = ds.resolve(world, "balan")
    assert lan.avatar_path and lan.family_question and lan.guardian_id
    real, fake = ds.resolve(world, "thuha"), ds.resolve(world, "nguyenthuha.2025")
    assert real.avatar_path == fake.avatar_path and real.display_name == fake.display_name   # tai khoan gia cung ten + anh
    assert len(ds.demo_accounts(world)) == len(ds.load()["actors"])
    assert len(ds.load()["scenarios"]) == 8
    assert all(st["type"] in ("message", "file", "broadcast", "report") for s in ds.load()["scenarios"] for st in s["steps"])


def test_scenario_7_no_false_alarm(world):
    res = run(world, "khong_bao_nham")
    assert all(r.get("level", 0) == 0 for r in res)
    assert set(victim_levels(world, "khong_bao_nham")) == {0}


def test_scenario_1_fake_relative(world):
    res = run(world, "gia_nguoi_than")
    lan, fake = ds.resolve(world, "balan"), ds.resolve(world, "nguyenthuha.2025")
    assert res[0]["level"] == 0 and res[1]["level"] == 1
    ev = GuardianEvent.query.filter_by(message_id=res[1]["message_id"]).one()
    assert ev.results["agent3"]["scenario"] == "gia_nguoi_than" and ev.results["decision"]["actions"]["family_hint"]
    from services import chat_service as cs
    conv = ds.conversation(lan, fake)
    assert cs.conversation_dto(conv, lan.id)["request"] is True                 # nguoi la -> Tin nhan cho


def test_scenarios_2_3_6_flagged(world):
    for sid in ("gia_cong_an", "gia_dien_luc", "gia_shipper"):
        res = run(world, sid)
        assert res[-1]["level"] >= 1, sid                               # tin cuoi bi AI 3 gan co
    m = Message.query.filter(Message.attachment_name == "XacMinhCongDan.apk").one()
    assert m.warning_level >= 2                                         # tin APK la lan 2 -> che + chan tai
    ev = GuardianEvent.query.filter_by(message_id=m.id).one()
    assert ev.results["decision"]["actions"]["block_apk"]
    evn = ds.resolve(world, "evn.cskh")
    last = Message.query.filter_by(sender_id=evn.id).order_by(Message.id.desc()).first()
    ev = GuardianEvent.query.filter_by(message_id=last.id).one()
    assert ev.results["decision"]["actions"]["blur_links"] and ev.results["text"]["urls"][0]["domain"] == "evn-thanhtoan.xyz"


def test_scenario_4_mass_messaging_and_report(world):
    res = run(world, "viec_nhe")
    assert res[0]["sent"] == 20 and all(lv == 1 for lv in res[0]["levels"])     # moi nguoi nhan 1 tin = lan 1
    scammer = ds.resolve(world, "tuyendung.online")
    ev = GuardianEvent.query.filter_by(actor_id=scammer.id).first()
    assert ev.results["text"]["changes"]                                         # da go chu chen "v.i.ệ.c n.h.ẹ"
    assert res[1]["saved"] is True                                               # bao cao = nhan train
    assert Report.query.filter_by(reported_id=scammer.id).count() == 1
    assert Feedback.query.filter_by(target_user_id=scammer.id, label="scam").count() == 1
    assert Notification.query.filter_by(actor_id=scammer.id, kind="herd").count() == 0   # khong con mien dich bay dan


def test_scenario_5_phase_tracking(world):
    res = run(world, "dau_tu_coin")
    phases = [GuardianEvent.query.filter_by(message_id=r["message_id"]).one().results["agent3"]["phase"] for r in res]
    order = ["none", "tiep_can", "tao_tin", "gay_ap_luc", "co_lap", "yeu_cau"]
    assert [order.index(p) for p in phases] == sorted(order.index(p) for p in phases)    # pha khong lui
    assert phases[-1] == "yeu_cau" and res[-1]["level"] >= 1


def test_demo_reset_and_api(world, app):
    run(world, "gia_dien_luc")
    ds.reset(world, "gia_dien_luc")
    evn = ds.resolve(world, "evn.cskh")
    assert Message.query.filter_by(sender_id=evn.id).count() == 0


def test_scenario_8_three_strikes_auto_block(world):
    res = run(world, "chan_3_lan")
    assert [r["level"] for r in res] == [1, 2, 3]
    lan, ha = ds.resolve(world, "balan"), ds.resolve(world, "thuha")
    assert Block.query.filter_by(blocker_id=lan.id, blocked_id=ha.id, source="guardian").count() == 1
    assert Notification.query.filter_by(user_id=ha.id, kind="guardian_block").count() == 1     # bao ca nguoi bi chan
    assert Notification.query.filter_by(user_id=lan.guardian_id, kind="guardian").count() >= 1   # nguoi giam ho duoc bao
    ds.reset(world, "chan_3_lan")                                       # lam moi: go chan, xoa hoi thoai
    assert Block.query.filter_by(blocker_id=lan.id, blocked_id=ha.id).count() == 0
