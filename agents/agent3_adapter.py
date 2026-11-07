"""AI 3 · Doc vi: cuoc tro chuyen nay co phai kich ban lua dao khong? - ADAPTER cho model DA TRAIN.

Khong tu viet model. Chon backend qua .env (AGENT3_BACKEND):
  local  : (mac dinh) goi mo hinh dang nap trong app (services/ai_client.py: TF-IDF + Linear SVM).
  http   : POST payload toi AGENT3_URL (timeout AGENT3_TIMEOUT), nhan JSON theo schema dau ra.
  python : import ham AGENT3_MODULE ("goi.module:ham"), goi ham(payload: dict) -> dict.
  mock   : luat don gian tren tu khoa tin hieu (dung khi tat model / backend loi).
Backend that loi / qua thoi gian -> TU ROI VE mock va ghi log rieng (logs/agent3.log).

An toan: noi dung tin nhan luon la DU LIEU trong payload, khong bao gio ghep vao chi dan he thong nao.
Dau ra duoc kiem tra (validate); thieu truong nao thi dung gia tri mac dinh an toan.

Hieu chinh ngu canh (backend local): mo hinh duoc train tren SMS, cham tin chat thuong ngay khong on dinh
(vd "Shop gui chi STK..." ~1.0). map_response() nhan xac suat goc voi he so ngu canh (nguoi gui la ban be + khong co
dau hieu gay ap luc -> giam manh) roi ket hop diem luat. Xac suat goc van luu trong model_prob.

Model nhan dien THEO KICH BAN (ca cuoc tro chuyen) sau nay: dung backend http / python, nhan nguyen payload
(conversation = toi da 20 tin gan nhat) va tra ve schema dau ra mac dinh (is_scam, risk_score, phase, scenario, ...).
"""
from __future__ import annotations

import importlib
import logging
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from agents.contracts import PHASES, SCENARIO_LABEL, SCENARIOS, Agent3Result
from agents.agent3_text import find_keywords, keyword_meta, normalize

log = logging.getLogger("dangnam.agent3")
_LOG_READY = False


def _setup_log():
    global _LOG_READY
    if _LOG_READY:
        return
    _LOG_READY = True
    try:
        d = Path(__file__).resolve().parents[1] / "logs"
        d.mkdir(exist_ok=True)
        h = RotatingFileHandler(d / "agent3.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    except OSError:
        pass


PHASE_ORDER = {p: i for i, p in enumerate(("none", "tiep_can", "tao_tin", "gay_ap_luc", "co_lap", "yeu_cau"))}
GREETING_RE = re.compile(r"\b(chao|xin chao|lam quen|ket ban|xin phep|hello|hi )")
FAMILY_RE = re.compile(r"\b(me oi|bo oi|ba oi|ong oi|me chuyen|bo chuyen|con dang|con can|con bi|chau dang|chau can|me cho con|bo cho con)\b")
POLICE_RE = re.compile(r"\b(cong an|vien kiem sat|toa an|co quan dieu tra|bo cong an|rua tien|truy na|lenh bat)\b")
BANK_EVN_RE = re.compile(r"\b(dien luc|evn|cskh|cham soc khach hang|ngan hang|tai khoan cua quy khach|no cuoc|cat dien)\b")
JOB_RE = re.compile(r"\b(viec nhe|luong cao|hoa hong|nhiem vu|cong tac vien|lam online)\b")
INVEST_RE = re.compile(r"\b(dau tu|coin|san giao dich|tien ao|usdt|loi nhuan|lai \d+|nap them|rut tien)\b")
SHIP_RE = re.compile(r"\b(ship|shipper|giao hang|phi ship|don hang|buu pham)\b")
DEPOSIT_RE = re.compile(r"\b(dat coc|coc truoc|tien coc)\b")

EXPLAIN = {
    "gia_cong_an": "Người này tự xưng là cơ quan công an / tòa án và nói bạn liên quan đến vụ án. Công an thật KHÔNG làm việc qua "
                   "tin nhắn, không bắt cài ứng dụng hay chuyển tiền để “xác minh”.",
    "gia_nguoi_than": "Tin nhắn nhờ chuyển tiền gấp và dặn giữ bí mật – đúng kiểu kẻ gian giả làm người thân. Hãy gọi lại cho "
                      "người thân bằng số quen thuộc hoặc hỏi Mật mã gia đình trước khi chuyển bất kỳ khoản nào.",
    "gia_ngan_hang_dien_luc": "Tin nhắn mạo danh ngân hàng / điện lực, dọa khóa tài khoản hoặc cắt điện để bạn bấm link và nộp tiền. "
                              "Hãy tự gọi số tổng đài in trên hóa đơn, không bấm link lạ.",
    "viec_nhe_luong_cao": "Lời mời “việc nhẹ lương cao” thường bắt nạp tiền làm nhiệm vụ rồi chiếm đoạt. Không có việc thật nào "
                          "trả hoa hồng cao mà phải nộp tiền trước.",
    "dau_tu_tien_ao": "Người này rủ đầu tư và khoe lãi cao. Sàn đầu tư giả thường cho rút ít lúc đầu, rồi giục nạp tiền lớn và khóa "
                      "tài khoản. Đừng nạp tiền.",
    "gia_shipper": "Shipper thật không yêu cầu quét mã QR lạ hay chuyển khoản “phí ship” cho người lạ. Hãy kiểm tra đơn hàng trong "
                   "ứng dụng mua sắm.",
    "lay_lai_tien": "Người hứa giúp lấy lại tiền đã bị lừa thường là kẻ lừa đảo lần hai. Hãy báo công an nơi cư trú.",
    "bat_coc_online": "Yêu cầu đặt cọc trước cho người lạ rất dễ mất tiền. Chỉ thanh toán qua kênh có bảo vệ người mua.",
    "khac": "Tin nhắn có dấu hiệu lừa đảo. Đừng chuyển tiền, đừng đọc mã OTP, đừng bấm link lạ.",
    "none": "Chưa thấy dấu hiệu lừa đảo rõ ràng.",
}


class Reader:
    def __init__(self, backend: str = "local", url: str = "", timeout: float = 15.0, module: str = ""):
        self.backend = backend if backend in ("local", "http", "python", "mock") else "local"
        self.url, self.timeout, self.module = url, timeout, module
        self._fn = None
        _setup_log()

    # ================================================================== dau vao
    @staticmethod
    def build_payload(conversation: list[dict], text: dict, is_friend: bool = False) -> dict:
        """Schema mac dinh gui cho AI 3.
        conversation: toi da 20 tin gan nhat [{"role": "sender|receiver", "text": str, "timestamp": ISO8601, "attachments": [...]}]
        text: tien xu ly tin hien tai (agents/agent3_text.analyze_text) · is_friend: nguoi gui la ban be cua nguoi nhan."""
        return {
            "conversation": conversation[-20:],
            "context": {"is_friend": bool(is_friend)},
            "text": {"normalized_text": text.get("normalized_text", ""), "urls": text.get("urls", []),
                     "bank_accounts": text.get("bank_accounts", []), "amounts": text.get("amounts", []),
                     "keywords": text.get("keywords", {})},
        }

    # ================================================================== chay
    @property
    def mode(self) -> str:
        return "mock" if self.backend == "mock" else "model"

    def analyze(self, payload: dict) -> Agent3Result:
        t0 = time.perf_counter()
        result, fallback = None, None
        if self.backend != "mock":
            try:
                raw = {"local": self._call_local, "http": self._call_http, "python": self._call_python}[self.backend](payload)
                result = self.map_response(raw, payload)
                result.backend, result.mode = self.backend, "model"
            except Exception as e:  # noqa: BLE001 - backend that loi -> du phong mock, app khong duoc crash
                fallback = f"{type(e).__name__}: {e}"[:300]
                log.warning("Agent3 backend=%s loi -> dung mock: %s", self.backend, fallback)
        if result is None:
            result = self.mock(payload)
            result.fallback_reason = fallback
        result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        log.info("Agent3 backend=%s mode=%s risk=%.2f phase=%s scenario=%s %.1fms%s", result.backend, result.mode,
                 result.risk_score, result.phase, result.scenario, result.latency_ms, f" fallback={fallback}" if fallback else "")
        return result

    @staticmethod
    def current_text(payload: dict) -> str:
        sender = [m for m in payload.get("conversation", []) if m.get("role") == "sender"]
        return (sender[-1]["text"] if sender else "").strip()

    def _call_local(self, payload: dict) -> dict:
        from services.ai_client import manager
        text = self.current_text(payload)
        if not text:
            return {"prob": 0.0, "flag": False, "model": manager.active, "empty": True}
        out = manager.predict(text)
        if out is None:
            raise RuntimeError("Chưa có mô hình AI 3 nào được nạp")
        prob, flag = out
        return {"prob": float(prob), "flag": bool(flag), "model": manager.active}

    def _call_http(self, payload: dict) -> dict:
        import requests
        if not self.url:
            raise RuntimeError("Thiếu AGENT3_URL")
        r = requests.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _call_python(self, payload: dict) -> dict:
        if self._fn is None:
            mod, _, fn = self.module.partition(":")
            if not mod or not fn:
                raise RuntimeError("AGENT3_MODULE phải có dạng goi.module:ham")
            self._fn = getattr(importlib.import_module(mod), fn)
        return self._fn(payload)

    # ================================================================== dau ra
    def map_response(self, raw: dict, payload: dict) -> Agent3Result:
        """Doi dau ra cua model ve Agent3Result. Sua ham nay cho khop model that cua ban."""
        if not isinstance(raw, dict):
            raise ValueError("Đầu ra AI 3 không phải JSON object")
        rules = analyze_rules(payload)
        if "prob" in raw:                                      # backend local: chi co xac suat -> hieu chinh ngu canh
            prob = _f(raw.get("prob"))
            factor = 1.0 if rules["pressure"] else (0.25 if rules["trusted"] else 0.7)
            calibrated = prob * factor
            risk = max(calibrated, rules["rule_score"])
            res = _build(risk, rules)
            res.model_name, res.model_prob, res.model_flag = raw.get("model"), round(prob, 4), bool(raw.get("flag"))
            res.calibration = {"factor": factor, "model_x_factor": round(calibrated, 4), "rule_score": round(rules["rule_score"], 4),
                               "pressure": rules["pressure"], "trusted": rules["trusted"]}
            return res
        # backend http / python: schema dau ra mac dinh -> validate tung truong, thieu thi dung mac dinh an toan
        risk = _f(raw.get("risk_score"), rules["rule_score"])
        res = _build(risk, rules)
        if isinstance(raw.get("is_scam"), bool):
            res.is_scam = raw["is_scam"] or res.is_scam
        if raw.get("phase") in PHASES:
            res.phase = raw["phase"]
        if raw.get("scenario") in SCENARIOS:
            res.scenario = raw["scenario"]
        if isinstance(raw.get("signals"), list):
            res.signals = [str(s)[:200] for s in raw["signals"][:12]] or res.signals
        if isinstance(raw.get("explanation_vi"), str) and raw["explanation_vi"].strip():
            res.explanation_vi = raw["explanation_vi"].strip()[:600]
        res.model_prob = risk
        return res

    def mock(self, payload: dict) -> Agent3Result:
        rules = analyze_rules(payload)
        res = _build(rules["rule_score"], rules)
        res.backend, res.mode = "mock", "mock"
        res.calibration = {"rule_score": round(rules["rule_score"], 4), "pressure": rules["pressure"], "trusted": rules["trusted"]}
        return res


# =========================================================================== #
# Luat dung chung: diem luat, pha, kich ban, tin hieu, giai thich
# =========================================================================== #
def _f(v, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, x)) if x == x else default


def _stage(groups: set, folded: str, has_money_entity: bool) -> str:
    if groups & {"otp", "cccd", "install_app"} or ("money_request" in groups and has_money_entity) or \
            ("money_request" in groups and groups & {"urgency", "secrecy"}):
        return "yeu_cau"
    if groups & {"secrecy", "channel_switch"}:
        return "co_lap"
    if "urgency" in groups:
        return "gay_ap_luc"
    if groups & {"high_profit", "authority", "prize", "refund"}:
        return "tao_tin"
    if GREETING_RE.search(folded + " "):
        return "tiep_can"
    return "none"


def analyze_rules(payload: dict) -> dict:
    tk = payload.get("text") or {}
    ctx = payload.get("context") or {}
    conv = payload.get("conversation") or []
    meta = keyword_meta()
    cur_groups = set((tk.get("keywords") or {}).keys())
    accounts, amounts = tk.get("bank_accounts") or [], tk.get("amounts") or []
    money_entity = bool(accounts or amounts)
    money = "money_request" in cur_groups or bool(accounts)

    # lich su phia nguoi gui -> pha + kich ban
    history = [m for m in conv if m.get("role") == "sender"]
    folded_all, phase = "", "none"
    for m in history:
        n = normalize(m.get("text", ""))
        g = set(find_keywords(n.folded).keys())
        st = _stage(g, n.folded, bool(re.search(r"\d{8,}", n.folded)))
        if PHASE_ORDER[st] > PHASE_ORDER[phase]:
            phase = st
        folded_all += " " + n.folded
    cur_stage = _stage(cur_groups, (tk.get("normalized_text") and normalize(tk["normalized_text"]).folded) or "", money_entity)
    if PHASE_ORDER[cur_stage] > PHASE_ORDER[phase]:
        phase = cur_stage

    pressure = bool({g for g in cur_groups if meta.get(g, {}).get("pressure")})
    trusted = bool(ctx.get("is_friend"))

    score = min(0.6, sum(meta[g]["weight"] for g in cur_groups if g in meta))
    if accounts:
        score += 0.1
    if phase == "yeu_cau" and money and PHASE_ORDER.get(cur_stage, 0) >= PHASE_ORDER["tao_tin"]:
        score += 0.1
    if "authority" in cur_groups and cur_groups & {"money_request", "otp", "cccd", "install_app"}:
        score += 0.15
    if trusted and not pressure:
        score *= 0.5
    score = min(score, 0.97)

    # kich ban
    scenario = "none"
    if POLICE_RE.search(folded_all):
        scenario = "gia_cong_an"
    elif FAMILY_RE.search(folded_all) and money and (not trusted or pressure):
        scenario = "gia_nguoi_than"
    elif BANK_EVN_RE.search(folded_all):
        scenario = "gia_ngan_hang_dien_luc"
    elif JOB_RE.search(folded_all):
        scenario = "viec_nhe_luong_cao"
    elif INVEST_RE.search(folded_all):
        scenario = "dau_tu_tien_ao"
    elif SHIP_RE.search(folded_all) and money:
        scenario = "gia_shipper"
    elif "refund" in cur_groups:
        scenario = "lay_lai_tien"
    elif DEPOSIT_RE.search(folded_all):
        scenario = "bat_coc_online"

    signals = [meta[g]["label"] for g in cur_groups if g in meta]
    evidence = []
    if accounts and money:
        evidence.append(f"Tin nhắn kèm số tài khoản {accounts[0]} và yêu cầu chuyển tiền.")
    if tk.get("urls") and pressure:
        signals.append("Có đường link kèm lời thúc giục")
    return {"rule_score": score, "phase": phase, "scenario": scenario, "signals": list(dict.fromkeys(signals)),
            "evidence": evidence, "pressure": pressure, "trusted": trusted}


def _build(risk: float, rules: dict) -> Agent3Result:
    risk = round(max(0.0, min(1.0, risk)), 4)
    scenario = rules["scenario"]
    if risk >= 0.35 and scenario == "none":
        scenario = "khac"
    if risk < 0.35 and not rules["evidence"]:
        scenario = "none"
    phase = rules["phase"] if (risk >= 0.2 or rules["phase"] in ("tiep_can",)) else "none"
    if risk < 0.35 and rules["trusted"]:
        phase = "none"
    parts = [EXPLAIN[scenario]] + rules["evidence"][:2]
    if scenario == "none" and risk >= 0.2:
        parts = ["Có vài dấu hiệu cần để ý, nhưng chưa đủ để kết luận lừa đảo. Hãy thận trọng nếu được nhờ chuyển tiền."]
    return Agent3Result(is_scam=risk >= 0.5, risk_score=risk, phase=phase, scenario=scenario,
                        signals=rules["signals"][:10], explanation_vi=" ".join(parts))


def scenario_label(s: str) -> str:
    return SCENARIO_LABEL.get(s, s)


def make_reader() -> Reader:
    from config import Config
    return Reader(Config.AGENT3_BACKEND, Config.AGENT3_URL, Config.AGENT3_TIMEOUT, Config.AGENT3_MODULE)


reader = make_reader()
