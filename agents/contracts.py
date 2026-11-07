"""Hop dong du lieu vao / ra cua AI 3 va bo quyet dinh. Thay model chi can giu dung cac dataclass nay."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PHASES = ("tiep_can", "tao_tin", "gay_ap_luc", "co_lap", "yeu_cau", "none")
SCENARIOS = ("gia_cong_an", "gia_nguoi_than", "gia_ngan_hang_dien_luc", "viec_nhe_luong_cao", "dau_tu_tien_ao",
             "gia_shipper", "lay_lai_tien", "bat_coc_online", "khac", "none")
PHASE_LABEL = {"tiep_can": "Tiếp cận", "tao_tin": "Tạo lòng tin", "gay_ap_luc": "Gây áp lực", "co_lap": "Cô lập nạn nhân",
               "yeu_cau": "Yêu cầu tiền / thông tin", "none": "Không có"}
SCENARIO_LABEL = {"gia_cong_an": "Giả danh công an", "gia_nguoi_than": "Giả người thân vay tiền",
                  "gia_ngan_hang_dien_luc": "Giả ngân hàng / điện lực", "viec_nhe_luong_cao": "Việc nhẹ lương cao",
                  "dau_tu_tien_ao": "Đầu tư tiền ảo", "gia_shipper": "Giả shipper thu phí", "lay_lai_tien": "Hứa lấy lại tiền đã mất",
                  "bat_coc_online": "Bắt cọc online", "khac": "Kịch bản lừa đảo khác", "none": "Không phát hiện"}


class Contract:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# AI 3 - Doc vi
# --------------------------------------------------------------------------- #
@dataclass
class Agent3Result(Contract):
    is_scam: bool = False
    risk_score: float = 0.0
    phase: str = "none"
    scenario: str = "none"
    signals: list[str] = field(default_factory=list)
    explanation_vi: str = ""
    mode: str = "mock"                                             # model | mock
    backend: str = "mock"                                          # local | http | python | mock
    model_name: str | None = None
    model_prob: float | None = None                                # xac suat goc cua mo hinh (truoc hieu chinh ngu canh)
    model_flag: bool | None = None
    calibration: dict = field(default_factory=dict)
    fallback_reason: str | None = None
    latency_ms: float = 0.0


# --------------------------------------------------------------------------- #
# Bo quyet dinh
# --------------------------------------------------------------------------- #
@dataclass
class Decision(Contract):
    level: int = 0                                                 # 0..3 = so lan (toi da 3)
    rule_level: int = 0                                            # muc do nghiem trong theo diem AI 3 (Hoi Ve si)
    counter_level: int = 0                                         # lan thu may (khong gioi han)
    flagged: bool = False                                          # tang bo dem cong don
    reasons: list[str] = field(default_factory=list)
    actions: dict = field(default_factory=dict)                    # mask, blur_links, copy_delay, block_apk, ...
