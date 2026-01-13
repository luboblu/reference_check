# modules/url_verifier.py

import re
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher


# ========= 工具 =========

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w\s]', '', s)
    return s.strip()


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


# ========= URL 類型判斷 =========

def classify_url_type(url: str) -> str:
    u = url.lower()

    if "doi.org" in u or re.search(r'10\.\d{4,9}/', u):
        return "doi"

    if any(k in u for k in ["arxiv.org", "acm.org", "ieee.org", "springer.com"]):
        return "academic"

    if any(k in u for k in ["github.com", "project", "software", "platform"]):
        return "software"

    return "generic"


# ========= 驗證主函數 =========

def verify_url_candidate(parsed_ref: dict, url: str):
    """
    回傳：
        level: verified | weak_verified | url_only | failed
        reason: str
    """

    if not url or not isinstance(url, str):
        return "failed", "invalid url"

    url_type = classify_url_type(url)

    try:
        r = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
    except Exception:
        return "failed", "request error"

    if r.status_code != 200:
        return "failed", f"http {r.status_code}"

    # 至此：網址「存在」
    # -------------------

    soup = BeautifulSoup(r.text, "html.parser")
    ref_title = parsed_ref.get("title", "")

    # ===== DOI / Academic：嘗試嚴格比對 =====
    if url_type in ("doi", "academic"):
        meta_title = None

        mt = soup.find("meta", {"name": "citation_title"})
        if mt and mt.get("content"):
            meta_title = mt["content"]

        if meta_title:
            sim = title_similarity(ref_title, meta_title)
            if sim >= 0.75:
                return "verified", "citation_title matched"
            else:
                return "weak_verified", "citation_title low similarity"

        # 沒 citation meta，但頁面存在
        return "weak_verified", "no citation meta"

    # ===== Software / Project =====
    if url_type == "software":
        page_title = soup.title.text if soup.title else ""
        if ref_title and ref_title.lower() in page_title.lower():
            return "verified", "project title matched"
        return "weak_verified", "software page alive"

    # ===== Generic 網站 =====
    return "url_only", "page alive"
