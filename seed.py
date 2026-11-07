"""Tao du lieu demo: ~30 nguoi dung binh thuong (anh dai dien sinh bang Pillow), ban be, bai dang, hoi thoai thuong ngay,
cac tai khoan cua 8 kich ban (data/scenarios.json).

    python seed.py              # tao du lieu demo
    python seed.py --reset      # xoa du lieu demo cu roi tao lai
    python seed.py --no-scan    # khong cho Ve si quet tin cu (nhanh hon)

Tin nhan cu duoc Ve si quet bang mo hinh AI 3 (TF-IDF + SVM) neu nap duoc, khong thi dung che do mock.
Moi STK / SDT / ten mien / IP trong du lieu demo deu la GIA.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import timedelta

from app import app
from config import MODEL_KEY
from db.database import db, utcnow
from db.models import FamilyMember, Post, PostComment, PostReaction, User
from services import demo_service as ds

COLORS = ["#0f7b6c", "#e4572e", "#7b3fe4", "#2e9e5b", "#d6336c", "#f08c00", "#0b7285", "#5f3dc4", "#1b74e4", "#c2255c"]
POST_COLORS = [("#0f7b6c", "#74c0a8"), ("#e8590c", "#ffd43b"), ("#364fc7", "#74c0fc"), ("#862e9c", "#f783ac"), ("#2b8a3e", "#a9e34b")]


def seed_world(model_key: str, reset: bool, scan: bool):
    from services.ai_client import manager
    rnd = random.Random(f"dangnam-{model_key}")
    data = ds.load()
    t0 = time.time()
    if scan:
        try:
            manager.load_blocking()
            print(f"  [AI 3] dung mo hinh {manager.active_name()} de quet tin cu")
        except Exception as e:  # noqa: BLE001
            print(f"  [AI 3] khong nap duoc mo hinh ({e}) -> Ve si dung che do mock")
    if reset:
        names = list(data["actors"]) + [u for u, _ in data["normal_users"]]
        for u in User.query.filter(User.model_key == model_key, User.username.in_(names)).all():
            db.session.delete(u)
        db.session.commit()
        print("  da xoa du lieu demo cu")

    # ---- nguoi dung binh thuong ----
    normals = []
    for i, (username, name) in enumerate(data["normal_users"]):
        u = ds.ensure_user(model_key, username, name, days=rnd.randint(120, 1500), color=COLORS[i % len(COLORS)],
                           bio=rnd.choice(["Yêu đời, thích đi đây đó", "Mê cà phê sáng", "Sinh viên năm cuối", "Dân văn phòng",
                                           "Thích nấu ăn", "Fan bóng đá"]),
                           birth_year=rnd.randint(1975, 2003), verified=rnd.random() < 0.3, phone=rnd.random() < 0.7,
                           is_demo=i < 3)
        normals.append(u)
    # ---- tai khoan kich ban ----
    actors = {}
    for username, spec in data["actors"].items():
        actors[username] = ds.ensure_user(model_key, username, spec["name"], days=spec.get("days", 400), color=spec.get("color", "#0f7b6c"),
                                          bio=spec.get("bio"), birth_year=spec.get("birth_year"), verified=spec.get("verified", False),
                                          phone=spec.get("phone", False), style=spec.get("avatar_style"),
                                          avatar_key="thuha" if spec.get("avatar_style") == "ha" else None,
                                          old_names=spec.get("old_names"), demo_ip=spec.get("demo_ip"))
    db.session.commit()

    # ---- ban be: do thi ngau nhien giua nguoi binh thuong + quan he kich ban ----
    good = normals + [actors[k] for k in ("balan", "thuha", "ongminh", "anhtuan", "chilinh", "minhanh", "hoanglong", "shop.mebong")]
    for u in good:
        for v in rnd.sample(good, 4):
            if v.id != u.id:
                ds.befriend(u, v, days=rnd.randint(30, 600))
    for a, b in data["friends"]:
        ds.befriend(actors[a], actors[b], days=500)
    for who, member, rel in data["family"]:
        if not FamilyMember.query.filter_by(user_id=actors[who].id, member_id=actors[member].id).first():
            db.session.add(FamilyMember(user_id=actors[who].id, member_id=actors[member].id, relation=rel))
    from werkzeug.security import generate_password_hash

    from routes.settings import family_answer_key
    for who, (q, a) in data["family_question"].items():
        actors[who].family_question, actors[who].family_answer_hash = q, generate_password_hash(family_answer_key(a))
    for who, guardian in data["guardians"]:
        actors[who].guardian_id = actors[guardian].id
    db.session.commit()

    # ---- bai dang + cam xuc + binh luan ----
    if Post.query.join(User, Post.user_id == User.id).filter(User.model_key == model_key).count() == 0:
        for i, u in enumerate(good):
            text = data["posts"][i % len(data["posts"])]
            img = None
            if i % 3 == 0:
                c1, c2 = POST_COLORS[i % len(POST_COLORS)]
                img = ds.make_post_image(f"{model_key}_{i}", text.split(",")[0][:28], c1, c2)
            p = Post(user_id=u.id, body=text, image_path=img, created_at=utcnow() - timedelta(hours=rnd.randint(1, 240)))
            db.session.add(p)
            db.session.flush()
            for v in rnd.sample(good, rnd.randint(1, 6)):
                if v.id != u.id:
                    db.session.add(PostReaction(post_id=p.id, user_id=v.id, kind=rnd.choice(["like", "like", "love", "haha"])))
            for v in rnd.sample(good, rnd.randint(0, 2)):
                if v.id != u.id:
                    db.session.add(PostComment(post_id=p.id, user_id=v.id, body=rnd.choice(["Hay quá!", "Tuyệt vời 👍", "Đẹp thế!", "Chúc mừng nha"]),
                                               created_at=p.created_at + timedelta(minutes=30)))
        db.session.commit()

    # ---- hoi thoai thuong ngay giua ban be (Ve si quet: phai ra muc 0) ----
    from services.chat_service import friend_ids
    normal_ids = {n.id for n in normals}
    for u in normals[:12]:
        for fid in [f for f in friend_ids(u.id) if f in normal_ids][:1]:
            v = db.session.get(User, fid)
            if ds.conversation(u, v).messages.count():
                continue
            day = rnd.uniform(1, 20)
            for k in range(3):
                a, b = (u, v) if k % 2 == 0 else (v, u)
                ds.send(a, b, rnd.choice(data["chitchat"]), days_ago=day - k * 0.01, process=scan)
    # ---- setup cua cac kich ban (vd lich su chat cua kich ban 7) ----
    for sc in data["scenarios"]:
        if sc.get("setup"):
            victim = ds.resolve(model_key, sc["victim"])
            if victim and not any(ds.conversation(ds.resolve(model_key, s["from"]), ds.resolve(model_key, s["to"])).messages.count()
                                  for s in sc["setup"]):
                ds.run_setup(model_key, sc, process=scan)
    db.session.commit()
    total = User.query.filter_by(model_key=model_key).count()
    print(f"  xong: {total} nguoi dung · {time.time() - t0:.1f}s")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")                # console Windows (cp1252) khong in duoc tieng Viet
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Tao du lieu + kich ban demo cho DangNam")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-scan", action="store_true")
    args = ap.parse_args()
    app.config["GUARDIAN_ASYNC"] = False                         # quet dong bo trong luc seed
    with app.app_context():
        from services.seed_feed import seed_feed
        n = seed_feed()
        if n:
            print(f"Bang tin gia: them {n} bai")
        seed_world(MODEL_KEY, args.reset, not args.no_scan)
    print("\nTai khoan demo (mat khau chung: %s):" % ds.load()["password"])
    for u, spec in ds.load()["actors"].items():
        print(f"  {u:<18} {spec['name']:<24} {spec.get('role', '')}")
    print("Nguoi dung thuong:", ", ".join(u for u, _ in ds.load()["normal_users"][:6]), "...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
