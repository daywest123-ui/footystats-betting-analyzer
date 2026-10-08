"""Keyless open-data football source.

Uses openfootball/football.json for fixtures/results and football-data.co.uk
for historical/current-season fallback. Current bookmaker scraping is not a
runtime dependency: if reliable odds are unavailable, the analyzer returns
NO BET instead of inventing or approximating a price.
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


def _football_data_matches() -> list[dict[str, Any]]:
    out = []
    for league in FOOTBALL_DATA:
        for row in _csv_rows(league):
            d = _parse_date(row.get("Date", ""))
            h, a = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
            if not d or not h or not a:
                continue
            hg, ag = _float(row.get("FTHG")), _float(row.get("FTAG"))
            hthg, htag = _float(row.get("HTHG")), _float(row.get("HTAG"))
            hc, ac = _float(row.get("HC")), _float(row.get("AC"))
            hy, ay = _float(row.get("HY")), _float(row.get("AY"))
            hr, ar = _float(row.get("HR")), _float(row.get("AR"))
            done = hg is not None and ag is not None
            out.append({
                "home": h, "away": a, "league": league, "date": d,
                "time": row.get("Time"), "finished": done,
                "home_goals": int(hg) if done else None,
                "away_goals": int(ag) if done else None,
                "home_ht_goals": int(hthg) if hthg is not None else None,
                "away_ht_goals": int(htag) if htag is not None else None,
                "home_corners": hc, "away_corners": ac,
                "home_yellow": hy, "away_yellow": ay,
                "home_red": hr, "away_red": ar,
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
    by_key = {(_norm(x["home"]), _norm(x["away"]), x["date"]): x for x in out}
    for m in fallback:
        key = (_norm(m["home"]), _norm(m["away"]), m["date"])
        if key not in by_key:
            out.append(m)
            by_key[key] = m
        else:
            target = by_key[key]
            for field, value in m.items():
                if target.get(field) in (None, "") and value not in (None, ""):
                    target[field] = value
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
    ht_home = ht_draw = ht_away = 0.0
    corner_over = card_over = corner_samples = card_samples = 0.0
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

        hthg, htag = m.get("home_ht_goals"), m.get("away_ht_goals")
        if hthg is not None and htag is not None:
            ht_result = "1" if hthg > htag else "2" if hthg < htag else "X"
            if not home:
                ht_result = {"1": "2", "2": "1", "X": "X"}[ht_result]
            ht_home += int(ht_result == "1")
            ht_draw += int(ht_result == "X")
            ht_away += int(ht_result == "2")

        hc, ac = m.get("home_corners"), m.get("away_corners")
        if hc is not None and ac is not None:
            corner_samples += 1
            corner_over += int(float(hc) + float(ac) >= 9)

        hy, ay = m.get("home_yellow"), m.get("away_yellow")
        hr, ar = m.get("home_red"), m.get("away_red")
        if any(m.get(k) is not None for k in ("home_yellow", "away_yellow", "home_red", "away_red")):
            card_samples += 1
            card_over += int(float(hy or 0) + float(ay or 0) + float(hr or 0) + float(ar or 0) >= 5)

    n = len(rows)
    ht_n = ht_home + ht_draw + ht_away
    return {
        "matches": n,
        "points_per_game": pts / n,
        "goal_diff_per_game": gd / n,
        "goals_for_per_game": gf_total / n,
        "goals_against_per_game": ga_total / n,
        "over25_rate": over / n,
        "btts_rate": btts / n,
        "ht_home_rate": ht_home / ht_n if ht_n else 0.33,
        "ht_draw_rate": ht_draw / ht_n if ht_n else 0.34,
        "ht_away_rate": ht_away / ht_n if ht_n else 0.33,
        "corners_over8_5_rate": corner_over / corner_samples if corner_samples else 0.50,
        "cards_over4_5_rate": card_over / card_samples if card_samples else 0.50,
        "corner_samples": int(corner_samples),
        "card_samples": int(card_samples),
        "source": "openfootball+football-data.co.uk",
    }


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
    # No live scraper is used here. Only a concrete CSV bookmaker price is
    # accepted; otherwise the caller must treat the market as NO BET.
    return _csv_fixture_odds(home, away, day)


def get_matches(status: str = "SCHEDULED", limit: int = 20):
    fixtures = today_fixtures() if status.upper() in {"SCHEDULED", "TIMED"} else []
    return {"matches": fixtures[:limit], "source": "openfootball/football.json"}
