"""Nap va chay mo hinh phat hien lua dao cua AI 3: TF-IDF + Linear SVM (ai_training/IDF_SVM).

He thong chi con 1 mo hinh nen `manager.active` luon la MODEL_KEY ("svm") - dung lam "the gioi" tai khoan (users.model_key).
Mo hinh duoc nap nen khi server khoi dong (`manager.preload()`), hoac nap ngay o lan du doan dau tien.
Nap that bai -> predict() tra None -> adapter AI 3 tu roi ve che do mock, app khong crash.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time

from config import AI_ROOT, MODEL_KEY, model_specs

log = logging.getLogger("dangnam.ai")
RETRY_AFTER = 60.0                      # nap loi -> 60 giay sau moi thu lai (khong lam cham moi tin nhan)


class SVMPredictor:
    """predict(text) -> (xac_suat_lua_dao, bi_gan_co)."""

    def __init__(self, path):
        sys.path.append(str(AI_ROOT / "IDF_SVM"))          # de joblib tim thay module `preprocess`
        import joblib
        import numpy as np

        self._np = np
        bundle = joblib.load(path)
        self.pipe, self.platt = bundle["pipeline"], bundle["platt"]
        self.decision_threshold = bundle.get("decision_threshold", 0.0)

    def predict(self, text: str) -> tuple[float, bool]:
        d = float(self.pipe.decision_function([text])[0])
        if self.platt is not None:
            prob = float(self.platt.predict_proba(self._np.array([[d]]))[0, 1])
        else:
            prob = float(1.0 / (1.0 + self._np.exp(-d)))
        return prob, d > self.decision_threshold          # nhan goc cua SVM: decision_function > nguong

    def close(self):
        self.pipe = self.platt = None


def _build(spec: dict):
    path = spec["path"]
    if path is None or not path.exists():
        raise FileNotFoundError(f"Khong tim thay mo hinh '{spec['name']}' (da train chua?): {path}")
    return SVMPredictor(path)


class ModelManager:
    def __init__(self):
        self._lock = threading.RLock()          # bao ve trang thai
        self._infer_lock = threading.Lock()     # moi lan chi 1 luong chay suy luan
        self._predictor = None
        self.active: str = MODEL_KEY
        self.loading: bool = False
        self.error: str | None = None
        self._failed_at: float | None = None
        self.load_seconds: float | None = None

    # ---- thong tin cho giao dien ----
    def spec(self) -> dict:
        return model_specs()[MODEL_KEY]

    def info(self) -> dict:
        """Thong tin mo hinh cho trang quan tri: ten, kich thuoc, chi so tren tap test."""
        spec = self.spec()
        metrics, size = {}, None
        run = spec["run"]
        if run and (run / "metrics.json").exists():
            try:
                m = json.loads((run / "metrics.json").read_text(encoding="utf-8"))["test"]
                metrics = {"macro_f1": m["macro_f1"], "recall": m["recall_scam"], "precision": m["precision_scam"]}
            except (OSError, KeyError, ValueError):
                pass
        if spec["path"] and spec["path"].exists():
            size = round(spec["path"].stat().st_size / 2**20, 1)
        return {"key": MODEL_KEY, "name": spec["name"], "tagline": spec["tagline"], "kind": spec["kind"],
                "path": str(spec["path"]) if spec["path"] else None, "run": run.name if run else None,
                "available": size is not None, "size_mb": size, "metrics": metrics, **self.status()}

    def status(self) -> dict:
        with self._lock:
            return {"active": self.active, "ready": self._predictor is not None, "loading": self.loading,
                    "error": self.error, "load_seconds": self.load_seconds}

    def ready(self) -> bool:
        return self._predictor is not None

    def active_name(self) -> str:
        return self.spec()["name"]

    # ---- nap ----
    def _load(self) -> None:
        with self._lock:
            if self._predictor is not None or self.loading:
                return
            if self._failed_at and time.time() - self._failed_at < RETRY_AFTER:
                return
            self.loading, self.error = True, None
        t0 = time.time()
        try:
            new = _build(self.spec())
            new.predict("khoi dong")                      # chay thu 1 lan de lam nong
            with self._lock:
                self._predictor, self._failed_at = new, None
                self.load_seconds = round(time.time() - t0, 2)
            log.info("Da nap mo hinh %s trong %.1fs", MODEL_KEY, time.time() - t0)
        except Exception as e:  # noqa: BLE001 - bao loi cho trang quan tri, AI 3 dung mock
            log.exception("Nap mo hinh %s that bai", MODEL_KEY)
            with self._lock:
                self.error, self._failed_at = f"{type(e).__name__}: {e}", time.time()
        finally:
            with self._lock:
                self.loading = False

    def preload(self) -> None:
        """Nap nen khi server khoi dong (khong chan giao dien)."""
        threading.Thread(target=self._load, daemon=True, name="load-svm").start()

    def load_blocking(self) -> None:
        """Dung cho script (seed): nap xong moi tra ve; loi thi nem RuntimeError."""
        self._failed_at = None
        self._load()
        if self._predictor is None:
            raise RuntimeError(self.error or "Khong nap duoc mo hinh")

    def set_predictor(self, predictor) -> None:
        """Gan predictor co san (dung trong test)."""
        with self._lock:
            self._predictor, self.loading, self.error, self._failed_at = predictor, False, None, None

    # ---- suy luan ----
    def predict(self, text: str) -> tuple[float, bool] | None:
        """Tra ve (xac_suat, bi_gan_co) hoac None neu khong co mo hinh / van ban rong."""
        if not text or not text.strip():
            return None
        if self._predictor is None:
            self._load()                                  # lan dau: nap ngay (SVM ~1 giay)
            for _ in range(200):                          # luong khac dang nap (preload): cho toi da 10 giay
                if not self.loading:
                    break
                time.sleep(0.05)
        with self._infer_lock:
            predictor = self._predictor
            if predictor is None:
                return None
            return predictor.predict(text)


manager = ModelManager()
