"""Free external football-prediction evidence layer.

The sources are treated as independent external signals, never as ground truth.
Only explicit match-level tips/confidence values found on a public page are
accepted; generic page text is not converted into a prediction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

TIMEOUT = 6
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FootballAnalyzer/1.0)"}


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str


SOURCES = (
    Source("statsbet", "StatsBet", "https://statsbet.org/football/predictions"),
    Source("pitchdeep", "PitchDeep", "https://www.pitchdeep.com/"),
    Source("xgaura", "xGaura", "https://www.xgaura.com/today-predictions"),
    Source("predictionsfooty", "Predictions Footy", "https://predictionsfooty.com/"),
    Source("kingsodds", "Kings Odds", "https://www.kingsodds.com/predictions/today"),
)

# These pages are daily prediction indexes. Do not download the same page once
# per fixture; one request per source is enough for an analysis run.
_PAGE_CACHE: dict[str, dict[str, Any]] = {}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _strip_html(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _team_tokens(name: str) -> list[str]:
    n = _norm(name)
    return [n, n.replace("fc", ""), n.replace("women", ""), n.replace("united", "")]


def _contains_match(text: str, home: str, away: str) -> bool:
    n = _norm(text)
    h = [x for x in _team_tokens(home) if len(x) >= 5]
    a = [x for x in _team_tokens(away) if len(x) >= 5]
    return any(x in n for x in h) and any(x in n for x in a)


def _parse_tip(window: str, home: str, away: str) -> tuple[str | None, float | None]:
    low = window.lower()
    tip = None
    if re.search(r"\b(home win|home team win|1x2\s*[:=-]?\s*1|tip\s*[:=-]?\s*1)\b", low):
        tip = "1"
    elif re.search(r"\b(away win|away team win|1x2\s*[:=-]?\s*2|tip\s*[:=-]?\s*2)\b", low):
        tip = "2"
    elif re.search(r"\b(draw|tip\s*[:=-]?\s*x|1x2\s*[:=-]?\s*x)\b", low):
        tip = "X"
    elif re.search(r"\b(btts\s*(yes|y)|both teams to score)\b", low):
        tip = "BTTS_YES"
    elif re.search(r"\b(btts\s*(no|n)|both teams not to score)\b", low):
        tip = "BTTS_NO"
    elif re.search(r"\b(over\s*2\.5|o2\.5)\b", low):
        tip = "OVER_2_5"
    elif re.search(r"\b(under\s*2\.5|u2\.5)\b", low):
        tip = "UNDER_2_5"

    conf = None
    m = re.search(
        r"(?:confidence|conf\.?|probability|model prob\.?|win rate)\s*[:=-]?\s*(\d{1,3}(?:\.\d+)?)\s*%",
        low,
    )
    if m:
        conf = float(m.group(1)) / 100.0
    return tip, conf


def _fetch_page(source: Source) -> dict[str, Any]:
    cached = _PAGE_CACHE.get(source.key)
    if cached is not None:
        return cached

    base: dict[str, Any] = {
        "source": source.key,
        "name": source.name,
        "url": source.url,
        "status": "UNAVAILABLE",
        "http_status": None,
        "text": "",
    }
    try:
        r = requests.get(source.url, headers=HEADERS, timeout=TIMEOUT)
        base["http_status"] = r.status_code
        if r.status_code != 200:
            base["status"] = f"HTTP_{r.status_code}"
        else:
            base["status"] = "OK"
            base["text"] = _strip_html(r.text)
    except requests.RequestException as exc:
        base["status"] = "REQUEST_ERROR"
        base["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        base["status"] = "PARSE_ERROR"
        base["error"] = f"{type(exc).__name__}: {exc}"

    _PAGE_CACHE[source.key] = base
    return base


def _match_window(text: str, home: str, away: str) -> str:
    """Return a bounded raw-text context around the fixture.

    Search the raw text rather than using offsets from normalized text, because
    stripping punctuation changes string positions.
    """
    lowered = text.casefold()
    positions: list[int] = []
    for token in (home, away):
        raw = str(token or "").strip()
        if len(raw) >= 5:
            pos = lowered.find(raw.casefold())
            if pos >= 0:
                positions.append(pos)

    if not positions:
        # Fallback to a normalized-text containment check; use the page prefix
        # as evidence rather than inventing a precise location.
        return text[:3400]

    pos = min(positions)
    return text[max(0, pos - 1200): pos + 2200]


def fetch_source(source: Source, home: str, away: str) -> dict[str, Any]:
    page = _fetch_page(source)
    base = {
        "source": source.key,
        "name": source.name,
        "url": source.url,
        "status": page.get("status", "UNAVAILABLE"),
        "tip": None,
        "confidence": None,
        "match_found": False,
    }
    if page.get("http_status") is not None:
        base["http_status"] = page["http_status"]
    if page.get("error"):
        base["error"] = page["error"]

    text = page.get("text", "")
    if not text:
        return base

    if not _contains_match(text, home, away):
        base["status"] = "MATCH_NOT_FOUND_ON_PUBLIC_PAGE"
        return base

    base["match_found"] = True
    window = _match_window(text, home, away)
    tip, conf = _parse_tip(window, home, away)
    base.update({"tip": tip, "confidence": conf})
    base["status"] = "OK" if tip else "MATCH_FOUND_NO_EXPLICIT_TIP"
    base["evidence"] = window[:1200]
    return base


def analyze_match(
    home: str,
    away: str,
    enabled: tuple[str, ...] | None = None,
    *,
    reset_cache: bool = False,
) -> dict[str, Any]:
    if reset_cache:
        _PAGE_CACHE.clear()

    selected = [s for s in SOURCES if enabled is None or s.key in enabled]
    rows = [fetch_source(s, home, away) for s in selected]
    votes = [
        r for r in rows
        if r.get("tip") in {
            "1", "X", "2", "BTTS_YES", "BTTS_NO", "OVER_2_5", "UNDER_2_5"
        }
    ]
    by_tip: dict[str, int] = {}
    for row in votes:
        by_tip[row["tip"]] = by_tip.get(row["tip"], 0) + 1

    return {
        "status": "OK" if rows else "NO_SOURCES",
        "sources": rows,
        "explicit_vote_count": len(votes),
        "consensus": sorted(by_tip.items(), key=lambda x: (-x[1], x[0])),
        "notes": [
            "External sites are independent evidence, not ground truth.",
            "Only explicit match-level tips are counted as votes.",
            "Source failures never become negative evidence.",
            "No bookmaker odds are used to determine the football-side selection here.",
            "Each source page is fetched at most once per process run.",
        ],
    }
