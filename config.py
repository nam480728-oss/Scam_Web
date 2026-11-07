"""Cau hinh ung dung DangNam (mang xa hoi co Ve si AI canh bao lua dao)."""
import glob
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

AI_ROOT = BASE_DIR / "ai_training"


def _latest_run(pattern: str) -> Path | None:
    """Thu muc ket qua train day du moi nhat (bo qua cac lan chay --smoke-test)."""
    runs = sorted(p for p in glob.glob(str(AI_ROOT / pattern)) if "smoke" not in Path(p).name)
    return Path(runs[-1]) if runs else None


# AI 3 chi con 1 mo hinh: TF-IDF + Linear SVM. Cot users.model_key luon = MODEL_KEY.
MODEL_KEY = "svm"


def model_specs() -> dict[str, dict]:
    svm_run = _latest_run("IDF_SVM/outputs/tfidf_linear_svm_2*")
    return {
        MODEL_KEY: {
            "key": MODEL_KEY, "name": "TF-IDF + Linear SVM", "tagline": "Nhẹ, nhanh, giải thích được",
            "kind": "Học máy cổ điển", "run": svm_run,
            "path": Path(os.getenv("MODEL_SVM_PATH", svm_run / "model" / "tfidf_svm.joblib")) if svm_run else None,
            "icon": "⚡", "color": "#1b74e4",
        },
    }


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:@127.0.0.1:3306/data_scam?charset=utf8mb4")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_DIR = BASE_DIR / "uploads"
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024          # tran 12MB cho 1 request
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024            # 10MB / file
    IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
    FILE_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "zip", "rar", "7z"}
    VOICE_EXTS = {"webm", "ogg", "m4a", "mp3", "wav"}      # tin nhan thoai (ghi am tren trinh duyet)
    MAX_VOICE_SECONDS = 120
    MAX_VOICE_BYTES = 5 * 1024 * 1024

    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")   # mat khau trang quan tri (doi mo hinh AI)

    MAX_MESSAGE_LEN = 2000
    PAGE_SIZE = 40

    # ---- tai len (anh dai dien / anh bia / anh bai dang: cong khai trong app) ----
    PUBLIC_UPLOAD_DIR = BASE_DIR / "static" / "uploads"
    APK_EXTS = {"apk"}                                     # chi luu, KHONG BAO GIO mo / thuc thi

    # ---- Ve si: chay nen (False trong test de chay dong bo) ----
    GUARDIAN_ASYNC = os.getenv("GUARDIAN_ASYNC", "true").lower() == "true"

    # ---- Bo quyet dinh tin nhan (decision.py) ----
    LEVEL3_RISK = 0.85                                     # muc "rat nguy hiem" (chi de hien thi trong Hoi Ve si)
    LEVEL2_RISK = 0.60                                     # rui ro AI 3 >= nguong nay -> tin bi gan co (tinh 1 lan)

    # ---- AI 3 (doc vi - mo hinh da train) ----
    AGENT3_BACKEND = os.getenv("AGENT3_BACKEND", "local")  # local | http | python | mock
    AGENT3_URL = os.getenv("AGENT3_URL", "")
    AGENT3_TIMEOUT = float(os.getenv("AGENT3_TIMEOUT", "15"))
    AGENT3_MODULE = os.getenv("AGENT3_MODULE", "")         # vd my_model.infer:analyze

    # ---- Do uy tin nguoi gui loi moi ket ban (luat rieng, KHONG anh huong AI 3 / luat 3 lan) ----
    REPUTATION_BASE = 70                                   # diem goc, cong/tru roi kep 0..100
    REPUTATION_GREEN = 80                                  # >= : xanh (dang tin)
    REPUTATION_RED = 50                                    # <  : do (canh giac); con lai: vang
    # (so ngay toi da, diem) - tuoi tai khoan; bac cuoi la "lon hon moc truoc"
    REPUTATION_AGE_STEPS = [(1, -25), (7, -15), (30, -5), (180, 5), (365, 10), (None, 20)]
    # (so ban chung toi da, diem)
    REPUTATION_MUTUAL_STEPS = [(0, -10), (2, 0), (5, 10), (10, 15), (None, 20)]
    # (so lan doi ten toi da, diem)
    REPUTATION_RENAME_STEPS = [(0, 5), (1, 0), (2, -5), (4, -15), (None, -25)]

    # ---- Truy vet IP (chi quan tri vien xem) ----
    TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"   # chi tin X-Forwarded-For khi chay sau proxy
    IP_RETENTION_DAYS = int(os.getenv("IP_RETENTION_DAYS", "30"))      # IP tin nhan / dang nhap tu xoa sau N ngay
    GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH", "")         # file .mmdb (DB-IP Lite / GeoLite2 City) - tra cuu offline
    GEOIP_ONLINE = os.getenv("GEOIP_ONLINE", "false").lower() == "true"  # goi ip-api.com khi khong co file .mmdb
    GEOIP_ONLINE_URL = os.getenv("GEOIP_ONLINE_URL",
                                 "http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,isp")
    GEOIP_TIMEOUT = float(os.getenv("GEOIP_TIMEOUT", "3"))

    # ---- Demo ----
    DEMO_QUICK_LOGIN = os.getenv("DEMO_QUICK_LOGIN", "true").lower() == "true"   # nut dang nhap nhanh tai khoan demo

    # ---- WebRTC ----
    STUN_URLS = [u.strip() for u in os.getenv("STUN_URLS", "").split(",") if u.strip()]

    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 14
    JSON_AS_ASCII = False
