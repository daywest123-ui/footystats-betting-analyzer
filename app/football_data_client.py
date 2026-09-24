"""Keyless open-data football source.

Uses openfootball/football.json for fixtures/results and football-data.co.uk
as a historical/current-season fallback. Same-day odds prefer current
OddsHarvester prices; CSV odds are a fallback only.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import requests

TIMEOUT = 20
UA = "Mozilla/5.0 (compatible; OpenFootballAnalyzer/1.0)"
LOCAL_TZ = ZoneInfo("Europe/Istanbul")
OPENFOOTBALL = {
    "England Premier League": "en.1.json", "England Championship": "en.2.json",
    "England League One": "en.3.json", "England League Two": "en.4.json",
    "Germany Bundesliga": "de.1.json", "Germany 2. Bundesliga": "de.2.json",
    "Spain La Liga": "es.1.json", "Italy Serie A": "it.1.json",
    "France Ligue 1": "fr.1.json", "Netherlands Eredivisie": "nl.1.json",
    "Portugal Primeira Liga": "pt.1.json", "Greece Super League": "gr.1.json",
    "Turkey Super Lig": "tr.1.json",
}
OPENFOOTBALL_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/"
FOOTBALL_DATA = {
    "England Premier League": "E0", "England Championship": "E1",
    "England League One": "E2", "England League Two": "E3",
    "Germany Bundesliga": "D1", "Germany 2. Bundesliga": "D2",
    "Spain La Liga": "SP1", "Italy Serie A": "I1", "France Ligue 1": "F1",
    "Netherlands Eredivisie": "N1", "Portugal Primeira Liga": "P1",
    "Greece Super League": "G1", "Turkey Super Lig": "T1",
}
FOOTBALL_DATA_BASE = "https://www.football-data.co.uk/mmz4281/2627/"

_CSV_CACHE: dict[str, list[dict[str, Any]]] = {}


def _norm(v: str) -> str:
    v = re.sub(r"\b(fc|afc|cf|sc|calcio|club)\b", "", str(v), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", v.lower())


def _get(url: str) -> requests.Response:
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r


def _parse_date(v: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            pass
    return None


def _football_data_matches() -> list[dict[str, Any]]:
    out = []
    for league in FOOTBALL_DATA:
        for row in _csv_rows(league):
            d = _parse_date(row.get("Date", ""))
            h, a = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
            if not d or not h or not a:
                continue
            hg, ag = _float(row.get("FTHG")), _float(row.get("FTAG"))
            done = hg is not None and ag is not None
            out.append({
                "home": h, "away": a, "league": league, "date": d,
                "time": row.get("Time"), "finished": done,
                "home_goals": int(hg) if done else None,
                "away_goals": int(ag) if done else None,
                "source": "football-data.co.uk",
            })
    return out


def load_openfootball() -> list[dict[str, Any]]:
    out = []
    for league, file in OPENFOOTBALL.items():
        try:
            data = _get(OPENFOOTBALL_BASE + file).json()
            for m in data.get("matches", []):
                h, a = m.get("team1"), m.get("team2")
                d = _parse_date(m.get("date", ""))
                if not h or not a or not d:
                    continue
                score = m.get("score") if isinstance(m.get("score"), dict) else {}
                ft = score.get("ft") if isinstance(score, dict) else None
                done = isinstance(ft, list) and len(ft) == 2 and all(x is not None for x in ft)
                out.append({
                    "home": h.strip(), "away": a.strip(), "league": league, "date": d,
                    "time": m.get("time"), "finished": done,
                    "home_goals": int(ft[0]) if done else None,
                    "away_goals": int(ft[1]) if done else None,
                    "source": "openfootball/football.json",
                })
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue

    fallback = _football_data_matches()
    seen = {(_norm(x["home"]), _norm(x["away"]), x["date"]) for x in out}
    for m in fallback:
        key = (_norm(m["home"]), _norm(m["away"]), m["date"])
        if key not in seen:
            out.append(m)
            seen.add(key)
    return out


def today_fixtures(day: str | None = None) -> list[dict[str, Any]]:
    day = day or datetime.now(LOCAL_TZ).date().isoformat()
    return [m for m in load_openfootball() if m["date"] == day and not m["finished"]]


def recent_form(matches: list[dict[str, Any]], team: str, before: str, limit: int = 8) -> dict[str, Any]:
    key = _norm(team)
    rows = [
        m for m in matches
        if m["finished"] and m["date"] < before
        and (_norm(m["home"]) == key or _norm(m["away"]) == key)
    ]
    rows = sorted(rows, key=lambda x: x["date"], reverse=True)[:limit]
    if not rows:
        return {
            "matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0,
            "goals_for_per_game": 1.25, "goals_against_per_game": 1.25,
            "over25_rate": 0.5, "btts_rate": 0.5, "source": "openfootball"
        }

    pts = gd = gf_total = ga_total = over = btts = 0.0
    for m in rows:
        hg, ag = m["home_goals"], m["away_goals"]
        home = _norm(m["home"]) == key
        gf, ga = (hg, ag) if home else (ag, hg)
        pts += 3 if gf > ga else 1 if gf == ga else 0
        gd += gf - ga
        gf_total += gf
        ga_total += ga
        over += int(hg + ag >= 3)
        btts += int(hg > 0 and ag > 0)

    n = len(rows)
    return {
        "matches": n,
        "points_per_game": pts / n,
        "goal_diff_per_game": gd / n,
        "goals_for_per_game": gf_total / n,
        "goals_against_per_game": ga_total / n,
        "over25_rate": over / n,
        "btts_rate": btts / n,
        "source": "openfootball",
    }


def _float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _csv_rows(league: str) -> list[dict[str, Any]]:
    if league in _CSV_CACHE:
        return _CSV_CACHE[league]
    code = FOOTBALL_DATA.get(league)
    if not code:
        return []
    try:
        raw = _get(FOOTBALL_DATA_BASE + code + ".csv").content.decode("cp1252", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
    except (requests.RequestException, UnicodeError, csv.Error):
        rows = []
    _CSV_CACHE[league] = rows
    return rows


def _csv_fixture_odds(home: str, away: str, day: str) -> dict[str, float]:
    hk, ak = _norm(home), _norm(away)
    vals = {"home_win": [], "draw": [], "away_win": [], "over_2_5": [], "under_2_5": []}
    cols = {
        "home_win": ("B365H", "BWH", "IWH", "PSH", "WHH"),
        "draw": ("B365D", "BWD", "IWD", "PSD", "WHD"),
        "away_win": ("B365A", "BWA", "IWA", "PSA", "WHA"),
        "over_2_5": ("B365>2.5", "P>2.5", "Max>2.5"),
        "under_2_5": ("B365<2.5", "P<2.5", "Max<2.5"),
    }
    for league in FOOTBALL_DATA:
        for row in _csv_rows(league):
            if _parse_date(row.get("Date", "")) != day:
                continue
            if _norm(row.get("HomeTeam", "")) != hk or _norm(row.get("AwayTeam", "")) != ak:
                continue
            for key, names in cols.items():
                for col in names:
                    value = _float(row.get(col))
                    if value and value > 1:
                        vals[key].append(value)
            return {key: round(median(values), 4) for key, values in vals.items() if values}
    return {}


def fixture_odds(home: str, away: str, day: str) -> dict[str, float]:
    try:
        from app.odds_harvester_client import fixture_odds as current_fixture_odds
        live = current_fixture_odds(home, away, day)
        if live:
            return live
    except Exception as exc:
        print(f"OddsHarvester current odds unavailable: {type(exc).__name__}")
    return _csv_fixture_odds(home, away, day)


def get_matches(status: str = "SCHEDULED", limit: int = 20):
    fixtures = today_fixtures() if status.upper() in {"SCHEDULED", "TIMED"} else []
    return {"matches": fixtures[:limit], "source": "openfootball/football.json"}
