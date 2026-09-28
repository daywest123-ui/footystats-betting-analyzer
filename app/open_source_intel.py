"""Optional open-source football intelligence layer powered by DataFC/Sofascore.

This module is analysis-only. It adds historical HT/FT, first/second-half and
H2H evidence without replacing the existing FootyStats engines.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from datafc import search_data, team_match_history_data
except Exception:  # optional dependency / offline CI
    search_data = None
    team_match_history_data = None


SPECIAL_OUTCOMES = (
    "X/X", "X/1", "X/2", "1/X", "2/X", "0/0", "0/1", "0/2",
    "1/1", "2/2",
)


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _result(h: int, a: int) -> str:
    return "1" if h > a else "2" if h < a else "X"


def _team_rows(team_id: int, limit: int = 30) -> list[dict[str, Any]]:
    if team_match_history_data is None:
        return []
    try:
        df = team_match_history_data(team_id=team_id)
        if df is None or df.empty:
            return []
        rows = df.to_dict("records")
        rows = [r for r in rows if str(r.get("status", "")).lower() in {"ended", "finished", "complete", "completed"} or _num(r.get("home_score_normaltime")) is not None]
        rows.sort(key=lambda r: _num(r.get("start_timestamp")) or 0, reverse=True)
        return rows[:limit]
    except Exception:
        return []


def _find_team(name: str) -> tuple[int | None, str]:
    if search_data is None:
        return None, "DataFC unavailable"
    try:
        df = search_data(name, entity_type="team")
        if df is None or df.empty:
            return None, "team not found"
        # Prefer the closest textual match returned by DataFC.
        exact = df[df["entity_name"].astype(str).str.lower() == name.lower()]
        row = (exact.iloc[0] if not exact.empty else df.iloc[0])
        return int(row["entity_id"]), "ok"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _extract_match(row: dict[str, Any], team_name: str) -> dict[str, Any] | None:
    hg = _num(row.get("home_score_normaltime"))
    ag = _num(row.get("away_score_normaltime"))
    h1 = _num(row.get("home_score_period1"))
    a1 = _num(row.get("away_score_period1"))
    if None in (hg, ag, h1, a1):
        return None
    home = str(row.get("home_team", ""))
    away = str(row.get("away_team", ""))
    is_home = home.lower() == team_name.lower()
    if not is_home and away.lower() != team_name.lower():
        # Team-name aliases are common; the caller already selected this team's history.
        is_home = True
    return {
        "home": home, "away": away, "hg": int(hg), "ag": int(ag),
        "h1": int(h1), "a1": int(a1), "team_home": is_home,
        "ht": _result(int(h1), int(a1)), "ft": _result(int(hg), int(ag)),
        "second_half_goals": int(hg + ag - h1 - a1),
        "second_half_result": _result(
            int(hg - h1) if is_home else int(ag - a1),
            int(ag - a1) if is_home else int(hg - h1),
        ),
    }


def _rates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [r for r in rows if r]
    n = len(matches)
    if not n:
        return {"sample": 0}
    ht = Counter(r["ht"] for r in matches)
    ft = Counter(r["ft"] for r in matches)
    htft = Counter(f"{r['ht']}/{r['ft']}" for r in matches)
    return {
        "sample": n,
        "ht_draw_rate": round(ht["X"] / n, 4),
        "ht_scoreless_rate": round(sum(r["h1"] + r["a1"] == 0 for r in matches) / n, 4),
        "second_half_1plus_rate": round(sum(r["second_half_goals"] >= 1 for r in matches) / n, 4),
        "second_half_2plus_rate": round(sum(r["second_half_goals"] >= 2 for r in matches) / n, 4),
        "htft": {k: round(v / n, 4) for k, v in htft.items()},
        "ft": {k: round(v / n, 4) for k, v in ft.items()},
        "second_half_result": {k: round(v / n, 4) for k, v in second_half_result.items() if k},
    }


def analyze_match(home: str, away: str, recent_limit: int = 30) -> dict[str, Any]:
    """Return evidence for unusual HT/FT opportunities.

    No odds are invented here. A fair price is simply 1/model_probability.
    """
    hid, hstatus = _find_team(home)
    aid, astatus = _find_team(away)
    if hid is None or aid is None:
        return {
            "source": "DataFC/Sofascore", "status": "UNAVAILABLE",
            "home_lookup": hstatus, "away_lookup": astatus,
            "opportunities": [],
        }

    hrows = [_extract_match(r, home) for r in _team_rows(hid, recent_limit)]
    arows = [_extract_match(r, away) for r in _team_rows(aid, recent_limit)]
    hrows = [r for r in hrows if r]
    arows = [r for r in arows if r]

    h2h_rows = []
    for r in hrows:
        if (r["home"].lower() == away.lower() or r["away"].lower() == away.lower()
                or away.lower() in r["home"].lower() or away.lower() in r["away"].lower()):
            h2h_rows.append(r)
    for r in arows:
        if (r["home"].lower() == home.lower() or r["away"].lower() == home.lower()
                or home.lower() in r["home"].lower() or home.lower() in r["away"].lower()):
            if r not in h2h_rows:
                h2h_rows.append(r)

    # Recent team evidence: use the requested outcome only when both teams have
    # enough observations. H2H is a secondary component, never the sole signal.
    hr, ar, h2hr = _rates(hrows), _rates(arows), _rates(h2h_rows)
    home_venue_rows = [r for r in hrows if r.get("team_home") is True]
    away_venue_rows = [r for r in arows if r.get("team_home") is False]
    home_venue = _rates(home_venue_rows)
    away_venue = _rates(away_venue_rows)
    opportunities = []
    if min(hr.get("sample", 0), ar.get("sample", 0)) >= 12:
        for outcome in SPECIAL_OUTCOMES:
            hp = hr.get("htft", {}).get(outcome, 0.0)
            ap = ar.get("htft", {}).get(outcome, 0.0)
            h2hp = h2hr.get("htft", {}).get(outcome, 0.0) if h2hr.get("sample", 0) else 0.0
            # Conservative blend: recent home/away histories dominate; H2H only 15%.
            base = 0.425 * hp + 0.425 * ap + 0.15 * h2hp
            support = sum(x > 0 for x in (hp, ap, h2hp))
            if base >= 0.12 and support >= 2:
                opportunities.append({
                    "market": f"HT/FT {outcome}",
                    "model_probability": round(base, 4),
                    "model_probability_pct": round(base * 100, 2),
                    "fair_odds": round(1 / base, 2),
                    "home_history_pct": round(hp * 100, 2),
                    "away_history_pct": round(ap * 100, 2),
                    "h2h_pct": round(h2hp * 100, 2),
                    "h2h_sample": h2hr.get("sample", 0),
                    "support_sources": support,
                    "status": "VALUE_CANDIDATE_IF_MARKET_ODDS_EXCEED_FAIR_ODDS",
                })
    opportunities.sort(key=lambda x: x["model_probability"], reverse=True)

    return {
        "source": "DataFC/Sofascore",
        "status": "OK",
        "home_team_id": hid, "away_team_id": aid,
        "home_recent": hr, "away_recent": ar,
        "home_venue": home_venue, "away_venue": away_venue,
        "h2h": h2hr,
        "opportunities": opportunities[:10],
        "notes": [
            "Historical HT/FT rates come from DataFC/Sofascore match histories.",
            "H2H is secondary evidence and is down-weighted to 15%.",
            "No bookmaker price is fabricated; fair_odds = 1/model_probability.",
        ],
    }
