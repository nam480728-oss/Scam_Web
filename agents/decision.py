"""Bo quyet dinh muc canh bao cho TIN NHAN bang luat xac dinh (KHONG dung LLM). Nguong nam trong config.py.

Mot tin bi tinh la "PHAT HIEN LUA DAO" (gan co) CHI dua vao AI 3:
    - AI 3 ket luan lua dao (is_scam), hoac
    - diem rui ro cua AI 3 >= LEVEL2_RISK (0.6)

Moi tin gan co lam tang BO DEM cua nguoi gui trong cuoc chat; muc cua tin = so lan (toi da 3):
    Lan 1 : canh bao, tin VAN HIEN (link lam mo, tai APK phai xac nhan lai)
    Lan 2 : canh bao + CHE tin (bam moi xem), CHAN tai APK, copy STK phai dem nguoc 60 giay
    Lan 3 : TU DONG CHAN nguoi gui + bao cho ca 2 ben (go chan chi qua Khieu nai)
Tin khong gan co: muc 0. Khieu nai thanh cong -> bo dem ve 0 -> vong lap lai tu lan 1.
"""
from __future__ import annotations

from agents.contracts import Agent3Result, Decision

MAX_STRIKES = 3


def thresholds() -> dict:
    from config import Config
    return {"l3": Config.LEVEL3_RISK, "l2": Config.LEVEL2_RISK}


def decide(agent3: Agent3Result | None, text: dict | None = None, has_apk: bool = False,
           counter_before: int = 0) -> Decision:
    """agent3: ket qua AI 3 · text: ket qua tien xu ly (agents/agent3_text.analyze_text) · has_apk: tin co dinh kem .apk."""
    t = thresholds()
    text = text or {}
    risk = agent3.risk_score if agent3 else 0.0
    reasons: list[str] = []
    if agent3 and agent3.is_scam:
        reasons.append(f"AI 3 kết luận lừa đảo (rủi ro {risk:.2f})")
    elif risk >= t["l2"]:
        reasons.append(f"AI 3: rủi ro {risk:.2f} ≥ {t['l2']}")
    flagged = bool(reasons)
    strike = counter_before + 1 if flagged else 0
    level = min(strike, MAX_STRIKES) if flagged else 0
    if flagged:
        reasons.append(f"Lần thứ {strike} người này gửi tin lừa đảo trong cuộc chat"
                       + (" → tự động chặn" if strike >= MAX_STRIKES else ""))
    scenario = agent3.scenario if agent3 else "none"
    actions = {
        "mask": level >= 2,                                              # lan 2: che noi dung (bam moi xem)
        "blur_links": level >= 1 and bool(text.get("urls")),
        "copy_delay": 60 if level >= 2 else 0,                           # dem nguoc 60 giay truoc khi copy STK
        "block_apk": level >= 2 and has_apk,                             # lan 2 tro di: chan tai APK
        "confirm_apk": level == 1 and has_apk,                           # lan 1: tai APK phai xac nhan lai
        "block_sender": strike >= MAX_STRIKES,                           # lan 3: tu dong chan
        "family_hint": level >= 1 and scenario == "gia_nguoi_than",
    }
    # Muc do nghiem trong theo diem (chi de hien thi trong "Hoi Ve si") - KHONG quyet dinh so lan
    rule_level = 3 if risk >= t["l3"] else (2 if flagged else (1 if risk >= 0.35 else 0))
    return Decision(level=level, rule_level=rule_level, counter_level=strike, flagged=flagged, reasons=reasons,
                    actions=actions)
