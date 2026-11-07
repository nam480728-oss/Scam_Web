"""Lay IP nguoi dung tu request va dinh vi GAN DUNG (quoc gia / tinh-thanh / nha mang). Khong bao gio dinh vi toi dia chi.

Thu tu tra cuu:
  1. IP demo (data/scenarios.json -> demo_ip_geo)           geo_source = "demo"
  2. IP noi bo / localhost (127.x, 192.168.x, 10.x, ::1...)   geo_source = "private"
  3. File .mmdb offline (GEOIP_DB_PATH, can `maxminddb`)       geo_source = "mmdb"
  4. ip-api.com (chi khi GEOIP_ONLINE=true)                   geo_source = "online"
  5. Khong tra duoc                                            geo_source = "unknown"
Moi loi deu duoc nuot (ghi log) - dinh vi KHONG BAO GIO lam hong luong chat.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

from flask import Request, current_app

log = logging.getLogger("dangnam.ipgeo")
_DEMO_FILE = Path(__file__).resolve().parents[1] / "data" / "scenarios.json"
_mmdb_lock = threading.Lock()
_mmdb_reader = None
_mmdb_path = None


def client_ip(req: Request) -> str | None:
    """IP cua nguoi gui request. Chi tin X-Forwarded-For khi TRUST_PROXY=true (ProxyFix da gan vao remote_addr)."""
    ip = (req.remote_addr or "").strip()
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def user_agent(req: Request) -> str | None:
    ua = (req.headers.get("User-Agent") or "").strip()
    return ua[:255] or None


@lru_cache(maxsize=1)
def demo_geo() -> dict[str, dict]:
    try:
        data = json.loads(_DEMO_FILE.read_text(encoding="utf-8")).get("demo_ip_geo", {})
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def _empty(source: str, label: str | None = None) -> dict:
    return {"country": label, "region": None, "city": None, "isp": None, "source": source}


def _from_mmdb(ip: str, path: str) -> dict | None:
    global _mmdb_reader, _mmdb_path
    try:
        import maxminddb
    except ImportError:
        log.warning("Chua cai thu vien maxminddb (pip install maxminddb) - bo qua GEOIP_DB_PATH")
        return None
    with _mmdb_lock:
        if _mmdb_reader is None or _mmdb_path != path:
            _mmdb_reader, _mmdb_path = maxminddb.open_database(path), path
        rec = _mmdb_reader.get(ip)
    if not rec:
        return None

    def name(node):
        names = (node or {}).get("names") or {}
        return names.get("vi") or names.get("en")
    subs = rec.get("subdivisions") or [{}]
    return {"country": name(rec.get("country")), "region": name(subs[0]), "city": name(rec.get("city")),
            "isp": (rec.get("traits") or {}).get("isp") or rec.get("isp"), "source": "mmdb"}


def _from_online(ip: str, url: str, timeout: float) -> dict | None:
    import requests
    r = requests.get(url.format(ip=ip), timeout=timeout)
    r.raise_for_status()
    d = r.json()
    if d.get("status") != "success":
        return None
    return {"country": d.get("country"), "region": d.get("regionName"), "city": d.get("city"), "isp": d.get("isp"),
            "source": "online"}


def geolocate(ip: str | None) -> dict:
    """{country, region, city, isp, source} - vi tri gan dung cua IP."""
    if not ip:
        return _empty("unknown")
    demo = demo_geo().get(ip)
    if demo:
        return {"country": demo.get("country"), "region": demo.get("region"), "city": demo.get("city"),
                "isp": demo.get("isp"), "source": "demo"}
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return _empty("unknown")
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return _empty("private", "Mạng nội bộ / localhost")
    cfg = current_app.config
    try:
        if cfg.get("GEOIP_DB_PATH") and Path(cfg["GEOIP_DB_PATH"]).exists():
            out = _from_mmdb(ip, cfg["GEOIP_DB_PATH"])
            if out:
                return out
        if cfg.get("GEOIP_ONLINE"):
            out = _from_online(ip, cfg["GEOIP_ONLINE_URL"], cfg["GEOIP_TIMEOUT"])
            if out:
                return out
    except Exception:  # noqa: BLE001 - dinh vi loi khong duoc lam hong luong xu ly
        log.exception("Dinh vi IP %s that bai", ip)
    return _empty("unknown")


SOURCE_LABEL = {"demo": "IP demo", "private": "Mạng nội bộ", "mmdb": "CSDL offline", "online": "ip-api.com",
                "unknown": "Không xác định"}


def place(geo: dict) -> str:
    """Chuoi vi tri de hien thi: 'Quan 7, TP. Ho Chi Minh, Viet Nam'."""
    parts = [geo.get("city"), geo.get("region"), geo.get("country")]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out) or "Không xác định"
