"""Tien xu ly van ban cho AI 3: chuan hoa (chu thuong, go ky tu chen, doi teencode, ban khong dau) + trich xuat
nhung gi giao dien can (link de lam mo, STK de dem nguoc khi copy, so tien) + tu khoa tin hieu cho hieu chinh ngu canh.

    >>> normalize("V.i.ệ.c n.h.ẹ, ck cho e 200k nhé").normalized
    'việc nhẹ, chuyển khoản cho em 200k nhé'

Khong co danh sach den, QR, OCR, phan tich APK hay kiem tra ten mien: viec gan co chi dua vao AI 3.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from unidecode import unidecode

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
WORD_RE = re.compile(r"\w+", re.UNICODE)
# chu-cai don le noi nhau bang . - _ * · ' (vd "c.h.u.y.ể.n", "v-i-ệ-c"), it nhat 3 chu cai
SPLIT_LETTERS_RE = re.compile(r"(?<!\w)(?:[^\W\d_][.\-_*·'’]){2,}[^\W\d_](?!\w)", re.UNICODE)
# chu-cai don le cach nhau boi khoang trang, it nhat 4 chu (vd "c h u y e n")
SPACED_LETTERS_RE = re.compile(r"(?<!\w)(?:[^\W\d_] ){3,}[^\W\d_](?!\w)", re.UNICODE)
ZERO_WIDTH_RE = re.compile("[​-‏⁠﻿­]")
URLISH_RE = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,10}(?:/\S*)?", re.IGNORECASE)

TLDS = {"com", "vn", "net", "org", "info", "xyz", "top", "club", "online", "site", "icu", "vip", "live", "cc", "me", "io",
        "co", "biz", "shop", "click", "link", "work", "fun", "app", "dev", "gov", "edu", "asia", "buzz", "monster", "rest",
        "ly", "gl", "be", "tk", "ml", "ga", "cf", "gq", "store", "tech", "space", "website"}
URL_RE = re.compile(r"(?:https?://[^\s<>\"']+|www\.[^\s<>\"']+|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,10}(?:/[^\s<>\"']*)?)",
                    re.IGNORECASE)
DIGITS_RE = re.compile(r"(?<!\d)\d(?:[\d .\-]{6,24}\d)(?!\d)")
ACCOUNT_HINT_RE = re.compile(r"(so tai khoan|tai khoan|chuyen khoan|chuyen vao|stk|so tk|account|ngan hang|chu tk|chu tai khoan)")
PHONE_HINT_RE = re.compile(r"(goi|sdt|so dien thoai|dien thoai|hotline|lien he|zalo|nhan tin)")
AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(trieu|tr|k|nghin|ngan|d|dong|vnd|ty)\b")


# --------------------------------------------------------------------------- #
# Chuan hoa
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def teencode() -> dict[str, str]:
    d = json.loads((DATA_DIR / "teencode.json").read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in d.items() if not k.startswith("_")}


def fold(text: str) -> str:
    """Ban khong dau, chu thuong (dung de so tu khoa)."""
    return unidecode(text or "").lower()


@dataclass
class NormResult:
    original: str
    normalized: str                  # chu thuong, da go ky tu chen + doi teencode (con dau)
    folded: str                      # ban khong dau cua normalized
    changes: list[dict] = field(default_factory=list)   # [{"from": "c.h.u.y.ể.n", "to": "chuyển", "kind": "split"}]


def _join_split_letters(text: str, changes: list) -> str:
    def repl(m: re.Match) -> str:
        joined = re.sub(r"[.\-_*·'’ ]", "", m.group(0))
        changes.append({"from": m.group(0), "to": joined, "kind": "split"})
        return joined
    text = SPLIT_LETTERS_RE.sub(repl, text)
    return SPACED_LETTERS_RE.sub(repl, text)


def _expand_teencode(text: str, changes: list) -> str:
    table = teencode()

    def repl(m: re.Match) -> str:
        w = m.group(0)
        full = table.get(w)
        if full and full != w:
            changes.append({"from": w, "to": full, "kind": "teencode"})
            return full
        return w
    return WORD_RE.sub(repl, text)


def normalize(text: str | None) -> NormResult:
    original = text or ""
    s = unicodedata.normalize("NFC", ZERO_WIDTH_RE.sub("", original)).lower()
    changes: list[dict] = []
    kept: list[str] = []            # giu nguyen link / ten mien (khong doi teencode ben trong, vd t.me)

    def protect(m: re.Match) -> str:
        if not re.search(r"[a-z]", m.group(0)) or m.group(0).count(".") == 0:
            return m.group(0)
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"
    s = URLISH_RE.sub(protect, s)
    s = _join_split_letters(s, changes)
    s = _expand_teencode(s, changes)
    s = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return NormResult(original=original, normalized=s, folded=fold(s), changes=changes)


# --------------------------------------------------------------------------- #
# Trich xuat
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _keywords() -> dict:
    return json.loads((DATA_DIR / "keywords.json").read_text(encoding="utf-8"))["groups"]


def _clean_url(u: str) -> str:
    return u.rstrip(".,;:!?)]}>\"'")


def domain_of(url: str) -> str | None:
    u = url if re.match(r"^https?://", url, re.I) else "http://" + url
    try:
        host = (urlparse(u).hostname or "").lower().strip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or host.rsplit(".", 1)[-1] not in TLDS:
        return None
    return host


def find_urls(text: str) -> list[dict]:
    out, seen = [], set()
    for m in URL_RE.finditer(text or ""):
        raw = _clean_url(m.group(0))
        if re.fullmatch(r"[\d.]+", raw):                   # so thap phan, khong phai link
            continue
        dom = domain_of(raw)
        if not dom or raw.lower() in seen:
            continue
        seen.add(raw.lower())
        out.append({"url": raw, "domain": dom})
    return out


def find_accounts(folded: str) -> list[str]:
    """Day 8-19 chu so dung gan (40 ky tu) cac tu 'stk / tai khoan / chuyen khoan...'."""
    out = []
    hints = [m.span() for m in ACCOUNT_HINT_RE.finditer(folded)]
    if not hints:
        return out
    for m in DIGITS_RE.finditer(folded):
        digits = re.sub(r"\D", "", m.group(0))
        if not 8 <= len(digits) <= 19:
            continue
        s, e = m.span()
        near = False
        for hs, he in hints:
            if he <= s and s - he <= 40 and not PHONE_HINT_RE.search(folded[he:s]):    # "stk ... 0123456789"
                near = True
            elif hs >= e and hs - e <= 15:                                              # "0123456789 la stk"
                near = True
        if near and digits not in out:
            out.append(digits)
    return out


def find_amounts(folded: str) -> list[int]:
    mult = {"trieu": 1_000_000, "tr": 1_000_000, "k": 1_000, "nghin": 1_000, "ngan": 1_000, "ty": 1_000_000_000,
            "d": 1, "dong": 1, "vnd": 1}
    out = []
    for m in AMOUNT_RE.finditer(folded):
        num = m.group(1)
        if re.fullmatch(r"\d+[.,]\d{1,2}", num):              # 3.5 trieu / 1,5tr -> so thap phan
            num = num.replace(",", ".")
        else:                                                # 500.000d / 1,000,000 -> dau phan cach hang nghin
            num = num.replace(".", "").replace(",", "")
        try:
            val = float(num) * mult[m.group(2)]
        except ValueError:
            continue
        if val >= 1000:
            out.append(int(val))
    return out


def find_keywords(folded: str) -> dict[str, list[str]]:
    hits = {}
    for g, cfg in _keywords().items():
        found = [p for p in cfg["phrases"] if re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", folded)]
        if found:
            hits[g] = found
    return hits


def keyword_meta() -> dict:
    return {g: {"label": c["label"], "weight": c["weight"], "pressure": c["pressure"]} for g, c in _keywords().items()}


def analyze_text(text: str | None) -> dict:
    """Ket qua tien xu ly 1 tin: dua vao payload AI 3 + luu trong nhat ky Ve si."""
    norm = normalize(text)
    return {"normalized_text": norm.normalized, "changes": norm.changes, "urls": find_urls(text or ""),
            "bank_accounts": find_accounts(norm.folded), "amounts": find_amounts(norm.folded),
            "keywords": find_keywords(norm.folded)}
