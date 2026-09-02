"""API-Football odds client.

Requires API_FOOTBALL_KEY in environment. The free API-Football plan currently
advertises pre-match and in-play odds, subject to provider coverage/quota.
"""
from __future__ import annotations
import os
import requests

BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT = 20

MARKET_MAP = {
    "Match Winner": {"Home": "home_win", "Draw": "draw", "Away": "away_win"},
    "Both Teams Score": {"Yes": "btts_yes", "No": "btts_no"},
    "Goals Over/Under": {},
}


def _headers():
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured")
    return {"x-apisports-key": key, "Accept": "application/json"}


def get_fixture_odds(fixture_id: int | str) -> dict:
    r = requests.get(f"{BASE_URL}/odds", params={"fixture": fixture_id},
                     headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload


def extract_markets(payload: dict) -> dict[str, float]:
    """Return median decimal odds by normalized market key."""
    values: dict[str, list[float]] = {}
    for provider in payload.get("response") or []:
        for bookmaker in provider.get("bookmakers") or []:
            for bet in bookmaker.get("bets") or []:
                bet_name = str(bet.get("name") or "")
                for item in bet.get("values") or []:
                    name = str(item.get("value") or "")
                    raw = item.get("odd")
                    try:
                        odd = float(raw)
                    except (TypeError, ValueError):
                        continue
                    key = MARKET_MAP.get(bet_name, {}).get(name)
                    if not key:
                        # common totals format e.g. "Over 2.5"
                        normalized = name.lower().replace(" ", "_").replace(".", "_")
                        if bet_name == "Goals Over/Under" and normalized in {"over_1_5","over_2_5","over_3_5","under_2_5","under_3_5"}:
                            key = normalized
                    if key and odd > 1.0:
                        values.setdefault(key, []).append(odd)

    result = {}
    for key, odds in values.items():
        odds.sort()
        result[key] = odds[len(odds)//2]
    return result
