"""Bo dem canh bao cong don lan 1 -> 2 -> 3 (luat chi tiet: agents/decision.py).

  * Dem so tin bi AI 3 gan co cua MOI NGUOI GUI trong TUNG cuoc chat. Khieu nai thanh cong -> ve 0 (vong lap).
  * Muc cua tin = so lan (toi da 3). Lan 3: Ve si tu dong chan nguoi gui.
  * Chi NGUOI NHAN thay canh bao tren tin. Nguoi gui thay canh bao "di TO" tu lan 3.
Viec tang bo dem nam trong agents/orchestrator.py (chay nen).
"""
from __future__ import annotations

from db.database import db
from db.models import ScamCounter

MAX_LEVEL = 3
SELF_WARNING_TEXT = ("Hệ thống phát hiện bạn đang là đối tượng đi lừa đảo người khác, "
                     "hãy dừng lại không thì bạn sẽ đi TÒ")


def level_for(count: int) -> int:
    return min(max(count, 0), MAX_LEVEL)


def get_count(conversation_id: int, user_id: int) -> int:
    row = db.session.get(ScamCounter, (conversation_id, user_id))
    return row.flagged_count if row else 0


def conversation_state(conversation_id: int, viewer_id: int, other_id: int) -> dict:
    """Trang thai canh bao cua cuoc chat *tu goc nhin cua viewer*.

    warning:      muc canh bao do DOI PHUONG gay ra (viewer la nguoi nhan) - 0..3
    self_warning: True neu CHINH viewer da bi gan co tu 3 lan tro len (hien canh bao 'di to')
    """
    from sqlalchemy import func

    from db.models import Message
    other = get_count(conversation_id, other_id)
    mine = get_count(conversation_id, viewer_id)
    top = (db.session.query(func.max(Message.warning_level))
           .filter(Message.conversation_id == conversation_id, Message.sender_id == other_id).scalar() or 0)
    return {"warning": max(level_for(other), min(int(top), MAX_LEVEL)), "self_warning": level_for(mine) >= MAX_LEVEL}
