"""Open-source football intelligence layer powered by DataFC/Sofascore.

The module is analysis-only. It provides venue-aware HT/FT history, first/second-half
evidence and secondary H2H evidence. It never fabricates bookmaker prices.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from datafc import search_data, team_match_history_data
except Exception:
    search_data = None
    team_match_history_data = None


HTFT_OUTCOMES = (
    "1/1", "1/X", "1/2",
    "X/1", "X/X", "X/2",
    "2/1", "2/X", "2/2",
)


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _result(home_score: int, away_score: int) -> str:
    return "1" if home_score > away_score else "2" if home_score < away_score else "X"


def _team_rows(team_id: int, limit: int = 60) -> list[dict[str, Any]]:
    if team_match_history_data is None:
        return []
    try:
        frame = team_match_history_data(team_id=team_id)
        if frame is None or frame.empty:
            return []
        rows = frame.to_dict("records")
        rows = [
            row for row in rows
            if (
                str(row.get("status", "")).lower()
                in {"ended", "finished", "complete", "completed"}
                or _num(row.get("home_score_normaltime")) is not None
            )
        ]
        rows.sort(key=lambda row: _num(row.get("start_timestamp")) or 0, reverse=True)
        return rows[:limit]
    except Exception:
        return []


def _find_team(name: str) -> tuple[int | None, str]:
    if search_data is None:
        return None, "DataFC unavailable"
    try:
        frame = search_data(name, entity_type="team")
        if frame is None or frame.empty:
            return None, "team not found"
        exact = frame[frame["entity_name"].astype(str).str.lower() == name.lower()]
        row = exact.iloc[0] if not exact.empty else frame.iloc[0]
        return int(row["entity_id"]), "ok"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _extract_match(row: dict[str, Any]) -> dict[str, Any] | None:
    home_score = _num(row.get("home_score_normaltime"))
    away_score = _num(row.get("away_score_normaltime"))
    home_ht = _num(row.get("home_score_period1"))
    away_ht = _num(row.get("away_score_period1"))
    if None in (home_score, away_score, home_ht, away_ht):
        return None
    return {
        "home": str(row.get("home_team", "")),
        "away": str(row.get("away_team", "")),
        "hg": int(home_score),
        "ag": int(away_score),
        "h1": int(home_ht),
        "a1": int(away_ht),
        "team_home": None,
        "ht": _result(int(home_ht), int(away_ht)),
        "ft": _result(int(home_score), int(away_score)),
        "second_half_goals": int(home_score + away_score - home_ht - away_ht),
    }


def _venue_rows(rows: list[dict[str, Any]], team_name: str, venue: str) -> list[dict[str, Any]]:
    wanted = team_name.casefold()
    out = []
    for raw in rows:
        row = _extract_match(raw)
        if not row:
            continue
        home = row["home"].casefold()
        away = row["away"].casefold()
        if home == wanted:
            is_home = True
        elif away == wanted:
            is_home = False
        else:
            continue
        if (venue == "home" and is_home) or (venue == "away" and not is_home):
            row["team_home"] = is_home
            out.append(row)
    return out


def _reorient_for_team(row: dict[str, Any]) -> dict[str, Any]:
    if row["team_home"]:
        return row
    swapped = dict(row)
    swapped["ht"] = {"1": "2", "2": "1", "X": "X"}[row["ht"]]
    swapped["ft"] = {"1": "2", "2": "1", "X": "X"}[row["ft"]]
    swapped["home"], swapped["away"] = row["away"], row["home"]
    return swapped


def _rates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [r for r in rows if r]
    n = len(matches)
    if not n:
        return {"sample": 0, "htft": {}, "ht": {}, "ft": {}}
    ht = Counter(r["ht"] for r in matches)
    ft = Counter(r["ft"] for r in matches)
    htft = Counter(f"{r['ht']}/{r['ft']}" for r in matches)
    return {
        "sample": n,
        "ht_draw_rate": round(ht["X"] / n, 4),
        "ht_scoreless_rate": round(
            sum(r["h1"] + r["a1"] == 0 for r in matches) / n, 4
        ),
        "second_half_1plus_rate": round(
            sum(r["second_half_goals"] >= 1 for r in matches) / n, 4
        ),
        "second_half_2plus_rate": round(
            sum(r["second_half_goals"] >= 2 for r in matches) / n, 4
        ),
        "htft": {key: round(value / n, 4) for key, value in htft.items()},
        "ht": {key: round(value / n, 4) for key, value in ht.items()},
        "ft": {key: round(value / n, 4) for key, value in ft.items()},
    }


def _blend_htft(home_rates: dict[str, Any], away_rates: dict[str, Any],
                h2h_rates: dict[str, Any]) -> list[dict[str, Any]]:
    # Venue-aware team histories dominate. H2H remains a secondary 10% component.
    results: list[dict[str, Any]] = []
    for outcome in HTFT_OUTCOMES:
        hp = float(home_rates.get("htft", {}).get(outcome, 0.0))
        ap = float(away_rates.get("htft", {}).get(outcome, 0.0))
        h2hp = float(h2h_rates.get("htft", {}).get(outcome, 0.0))
        base = 0.45 * hp + 0.45 * ap + 0.10 * h2hp
        support = sum(value > 0 for value in (hp, ap, h2hp))
        if base <= 0:
            continue
        results.append({
            "market": f"HT/FT {outcome}",
            "model_probability": round(base, 6),
            "model_probability_pct": round(base * 100, 2),
            "fair_odds": round(1 / base, 2),
            "home_venue_history_pct": round(hp * 100, 2),
            "away_venue_history_pct": round(ap * 100, 2),
            "h2h_pct": round(h2hp * 100, 2),
            "h2h_sample": int(h2h_rates.get("sample", 0)),
            "support_sources": support,
            "status": "VALUE_CANDIDATE_IF_MARKET_ODDS_EXCEED_FAIR_ODDS"
            if support >= 2 else "LOW_SUPPORT",
        })
    return sorted(results, key=lambda item: item["model_probability"], reverse=True)


def _h2h_matches(home_rows: list[dict[str, Any]], away_rows: list[dict[str, Any]],
                 home: str, away: str) -> list[dict[str, Any]]:
    def matches_pair(row: dict[str, Any], a: str, b: str) -> bool:
        h = row["home"].casefold()
        aw = row["away"].casefold()
        return (
            (h == a.casefold() and aw == b.casefold())
            or (h == b.casefold() and aw == a.casefold())
            or (a.casefold() in h and b.casefold() in aw)
            or (b.casefold() in h and a.casefold() in aw)
        )

    seen: set[tuple[str, str, int, int, int, int]] = set()
    out = []
    for raw in home_rows + away_rows:
        row = _extract_match(raw)
        if not row or not matches_pair(row, home, away):
            continue
        key = (
            row["home"], row["away"], row["hg"], row["ag"],
            row["h1"], row["a1"],
        )
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def analyze_match(home: str, away: str, recent_limit: int = 60) -> dict[str, Any]:
    """Return venue-aware HT/FT evidence for one fixture."""
    home_id, home_status = _find_team(home)
    away_id, away_status = _find_team(away)
    if home_id is None or away_id is None:
        return {
            "source": "DataFC/Sofascore",
            "status": "UNAVAILABLE",
            "home_lookup": home_status,
            "away_lookup": away_status,
            "opportunities": [],
        }

    raw_home = _team_rows(home_id, recent_limit)
    raw_away = _team_rows(away_id, recent_limit)
    home_venue = [_reorient_for_team(r) for r in _venue_rows(raw_home, home, "home")]
    away_venue = [_reorient_for_team(r) for r in _venue_rows(raw_away, away, "away")]
    h2h = [_reorient_for_team(r) for r in _h2h_matches(raw_home, raw_away, home, away)]

    home_rates = _rates(home_venue)
    away_rates = _rates(away_venue)
    h2h_rates = _rates(h2h)

    opportunities = []
    if min(home_rates["sample"], away_rates["sample"]) >= 8:
        opportunities = _blend_htft(home_rates, away_rates, h2h_rates)
        opportunities = [
            item for item in opportunities
            if item["model_probability"] >= 0.08 and item["support_sources"] >= 2
        ][:9]

    return {
        "source": "DataFC/Sofascore",
        "status": "OK",
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_venue_recent": home_rates,
        "away_venue_recent": away_rates,
        "h2h": h2h_rates,
        "opportunities": opportunities,
        "htft_outcomes": list(HTFT_OUTCOMES),
        "notes": [
            "HT/FT uses venue-aware histories: home team home matches and away team away matches.",
            "H2H is secondary evidence with 10% maximum weight.",
            "Fair odds are derived only as 1/model_probability.",
            "No bookmaker price is fabricated.",
        ],
    }
