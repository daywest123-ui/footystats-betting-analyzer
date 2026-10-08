"""Live, keyless Nesine pre-match odds client.

The public bulletin endpoint is read-only from the analyzer's perspective.
Only concrete odds returned by Nesine are accepted; no synthetic odds are made.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

URL = "https://bulten.nesine.com/api/bulten/getprebultenfull"
TIMEOUT = 20
UA = "Mozilla/5.0 (compatible; MatchAnalyzerX/1.0)"

MT_MS = 1
MT_FIRST_HALF = 7
MT_HTFT = 5
MT_GOALS_25 = 12
MT_BTTS = 38
MT_CORNERS = 216
MT_CARDS = 49
MT_BTTS_OVER = 446


def _norm(value: str) -> str:
    value = str(value or "").lower()
    value = value.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
    value = value.replace("ü", "u").replace("ö", "o").replace("ç", "c")
    value = re.sub(r"\b(fc|afc|cf|sc|fk|club)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


TEAM_ALIASES = {
    "psv": {"psv", "psveindhoven"},
    "heerenveen": {"heerenveen", "scheerenveen", "sc heerenveen"},
    "westham": {"westham", "westhamunited"},
    "qpr": {"qpr", "queensparkrangers"},
    "dortmund": {"dortmund", "bdortmund", "borussiadortmund"},
    "werderbremen": {"werderbremen", "svwerderbremen"},
    "lens": {"lens", "rclens", "racingclubdelens"},
    "lyon": {"lyon", "olympiquelyonnais"},
    "moreirense": {"moreirense", "moreirensefc"},
    "gilvicente": {"gilvicente", "gilvicentefc"},
    "braga": {"braga", "sportingclubedebraga", "scbraga"},
    "sporting": {"sporting", "sportingcp", "sportinglisbon", "sportinglizbon", "sportingclubedeportugal"},
    "malaga": {"malaga", "malagacf"},
    "espanyol": {"espanyol", "rcdespanyol", "rcdespanyold ebarcelona"},
}


def _canonical(value: str) -> str:
    n = _norm(value)
    for key, aliases in TEAM_ALIASES.items():
        cleaned = {_norm(x) for x in aliases}
        if n in cleaned or any(alias in n or n in alias for alias in cleaned):
            return key
    return n


def _match_name(a: str, b: str) -> bool:
    a, b = _canonical(a), _canonical(b)
    if not a or not b:
        return False
    return a == b


def _odds_map(oca: list[dict[str, Any]]) -> dict[int, float]:
    out = {}
    for item in oca or []:
        try:
            n = int(item.get("N"))
            odd = float(item.get("O"))
            if odd > 1.0:
                out[n] = odd
        except (TypeError, ValueError):
            continue
    return out


@lru_cache(maxsize=2)
def _payload() -> dict[str, Any]:
    # CI can supply a browser-backed public snapshot. Prefer it because the
    # Nesine site can treat GitHub's outbound HTTP differently from Chromium.
    snapshot = Path("reports/nesine_prebulten.json")
    if snapshot.exists():
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            if (payload.get("sg") or {}).get("EA"):
                return payload
        except (OSError, ValueError):
            pass

    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        "Referer": "https://www.nesine.com/iddaa/futbol",
        "Origin": "https://www.nesine.com",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    # First open the public bulletin page so the session receives the same
    # cookies a normal browser gets, then request the JSON feed.
    cachebuster = __import__("time").time_ns()
    try:
        session = requests.Session()
        session.get("https://www.nesine.com/iddaa/futbol", headers=headers, timeout=TIMEOUT)
        r = session.get(f"{URL}?_={cachebuster}", headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
        if (payload.get("sg") or {}).get("EA"):
            return payload
    except (requests.RequestException, ValueError):
        pass

    # Browser-like fallback for bot/CDN differences on GitHub Actions.
    from curl_cffi import requests as curl_requests
    session = curl_requests.Session(impersonate="chrome")
    session.get("https://www.nesine.com/iddaa/futbol", headers=headers, timeout=TIMEOUT)
    r = session.get(f"{URL}?_={cachebuster}", headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _event_markets(event: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for market in event.get("MA") or []:
        mtid = market.get("MTID")
        odds = _odds_map(market.get("OCA") or [])
        if not odds:
            continue

        if mtid == MT_MS and {1, 2, 3}.issubset(odds):
            result["home_win"] = odds[1]
            result["draw"] = odds[2]
            result["away_win"] = odds[3]
        elif mtid == MT_FIRST_HALF and {1, 2, 3}.issubset(odds):
            result["first_half_home"] = odds[1]
            result["first_half_draw"] = odds[2]
            result["first_half_away"] = odds[3]
        elif mtid == MT_HTFT and len(odds) >= 9:
            # Nesine's published HT/FT column order:
            # 1/1, X/1, 2/1, 1/X, X/X, 2/X, 1/2, X/2, 2/2.
            order = (
                "htft_1_1", "htft_x_1", "htft_2_1",
                "htft_1_x", "htft_x_x", "htft_2_x",
                "htft_1_2", "htft_x_2", "htft_2_2",
            )
            for n, key in enumerate(order, 1):
                if n in odds:
                    result[key] = odds[n]
        elif mtid == MT_GOALS_25 and abs(float(market.get("SOV") or 0) - 2.5) < 1e-9 and {1, 2}.issubset(odds):
            result["under_2_5"] = odds[1]
            result["over_2_5"] = odds[2]
        elif mtid == MT_BTTS and {1, 2}.issubset(odds):
            result["btts_yes"] = odds[1]
            result["btts_no"] = odds[2]
        elif mtid == MT_CORNERS and abs(float(market.get("SOV") or 0) - 8.5) < 1e-9 and {1, 2}.issubset(odds):
            result["corners_under_8_5"] = odds[1]
            result["corners_over_8_5"] = odds[2]
        elif mtid == MT_CARDS and {1, 2}.issubset(odds):
            # MTID 49 is Nesine's total-card market.
            result["cards_under_4_5"] = odds[1]
            result["cards_over_4_5"] = odds[2]
        elif mtid == MT_BTTS_OVER and len(odds) >= 4 and abs(float(market.get("SOV") or 0) - 2.5) < 1e-9:
            result["btts_over_2_5"] = odds[2]
    return result


def get_fixture_odds(home: str, away: str, day: str) -> dict[str, float]:
    data = _payload()
    events = (data.get("sg") or {}).get("EA") or []
    candidates = [
        e for e in events
        if e.get("D") == day
        and _match_name(home, e.get("HN", ""))
        and _match_name(away, e.get("AN", ""))
    ]
    for event in candidates:
        odds = _event_markets(event)
        if odds:
            return odds
    return {}
