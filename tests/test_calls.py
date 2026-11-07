"""Kiem thu GD 4: cuoc goi WebRTC (signaling qua Socket.IO), lich su cuoc goi trong hoi thoai."""
import pytest

from db.models import Call, Message


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
    from services import call_service
    call_service.reset()


def events(client, name):
    return [e["args"][0] for e in client.get_received() if e["name"] == name]


def test_call_flow_signal_and_log(app, pair, sio):
    a, b, cid = pair
    ca, cb = sio(a), sio(b)
    ca.get_received(); cb.get_received()
    r = ca.emit("call:start", {"conversation_id": cid, "video": True}, callback=True)
    assert r["ok"] and r["call"]["outgoing"] and r["call"]["status"] == "ringing"
    call_id = r["call"]["id"]
    inc = events(cb, "call:incoming")
    assert inc and inc[0]["call"]["id"] == call_id and inc[0]["call"]["other"]["id"] == a.id
    assert "error" in cb.emit("call:start", {"conversation_id": cid, "video": True}, callback=True)   # dang ban
    assert cb.emit("call:accept", {"call_id": call_id}, callback=True)["ok"]
    assert events(ca, "call:accepted")[0]["call_id"] == call_id
    ca.emit("call:signal", {"call_id": call_id, "data": {"type": "offer", "sdp": {"type": "offer", "sdp": "v=0"}}})
    sig = events(cb, "call:signal")
    assert sig and sig[0]["data"]["type"] == "offer"
    assert events(ca, "call:signal") == []                                      # khong doi lai cho chinh minh
    cb.emit("call:end", {"call_id": call_id}, callback=True)
    for c in (ca, cb):
        got = c.get_received()
        assert any(e["name"] == "call:ended" and e["args"][0]["status"] == "ended" for e in got)
        assert any(e["name"] == "message:new" and e["args"][0]["message"]["kind"] == "call" for e in got)
    with app.app_context():
        call = Call.query.get(call_id)
        assert call.status == "ended" and call.answered_at and call.ended_at
        log = Message.query.filter_by(kind="call").one()
        assert "Cuộc gọi video" in log.body and log.call_id == call_id
    msgs = b.get(f"/api/conversations/{cid}/messages").get_json()["messages"]
    assert msgs[-1]["kind"] == "call"


def test_call_decline_missed_and_permissions(app, pair, sio, mk):
    a, b, cid = pair
    ca, cb = sio(a), sio(b)
    call_id = ca.emit("call:start", {"conversation_id": cid, "video": False}, callback=True)["call"]["id"]
    cb.emit("call:decline", {"call_id": call_id}, callback=True)
    with app.app_context():
        assert Call.query.get(call_id).status == "declined"
        assert "từ chối" in Message.query.filter_by(kind="call").one().body
    c = mk("carol")
    cc = sio(c)
    assert "error" in cc.emit("call:accept", {"call_id": call_id}, callback=True)       # nguoi ngoai
    assert "error" in cc.emit("call:start", {"conversation_id": cid, "video": True}, callback=True)
    b.post("/api/blocks", {"user_id": a.id})
    assert "error" in ca.emit("call:start", {"conversation_id": cid, "video": True}, callback=True)  # bi chan
    # nguoi goi dong cua so khi dang do chuong -> cuoc goi nho
    b.delete(f"/api/blocks/{a.id}")
    call2 = ca.emit("call:start", {"conversation_id": cid, "video": True}, callback=True)["call"]["id"]
    ca.disconnect()
    with app.app_context():
        assert Call.query.get(call2).status == "missed"


def test_call_pages(app, pair):
    a, b, cid = pair
    assert a.get(f"/call/new?conv={cid}&video=1").status_code == 200
    assert a.get("/call/new?conv=99999").status_code == 404
    assert a.get("/call/12345").status_code == 404
