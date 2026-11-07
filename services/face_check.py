"""Kiem tra anh chup truc tiep khi khieu nai: dem so khung co khuon mat (OpenCV Haar cascade, chay CPU, khong can model).

Day KHONG phai phat hien deepfake - chi dam bao nguoi chup co lo mat. Cung voi do chuyen dong giua cac khung
(services/appeal_service._motion) de chong gio anh in / anh tinh.
"""
from __future__ import annotations

import logging

log = logging.getLogger("dangnam.face_check")
_cascade = None


def _detector():
    global _cascade
    if _cascade is None:
        import cv2
        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _cascade


def count_faces(images) -> int:
    """So khung (anh PIL) thay it nhat 1 khuon mat. Loi OpenCV -> 0 (khieu nai yeu cau chup lai, khong sap app)."""
    try:
        import cv2
        import numpy as np
        det = _detector()
        n = 0
        for im in images:
            gray = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
            side = min(gray.shape[:2])
            faces = det.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(max(40, side // 8),) * 2)
            n += 1 if len(faces) else 0
        return n
    except Exception:  # noqa: BLE001
        log.exception("Khong dem duoc khuon mat")
        return 0
