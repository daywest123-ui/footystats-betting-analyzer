"""Evidence-gated multi-sport coupon scanner.

Uses API-Sports for same-day fixtures and, when available, real pre-match odds.
A match is NOT placed in a coupon merely because it exists: it must have
usable bookmaker odds. This avoids the previous fake 0.53/0.56 scores.
The module is analysis-only and never places bets.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
TIMEOUT = 20
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

SPORTS = {
    "football": {"base": "https://v3.football.api-sports.io", "endpoint": "fixtures", "odds": "odds", "id_key": "fixture"},
    "basketball": {"base": "https://v1.basketball.api-sports.io", "endpoint": "games", "odds": "odds", "id_key": "game"},
    "volleyball": {"base": "https://v1.volleyball.api-sports.io", "endpoint": "games", "odds": "odds", "id_key": "game"},
    "hockey": {"base": "https://v1.hockey.api-sports.io", "endpoint": "games", "odds": "odds", "id_key": "game"},
}


def api_get(sport: str, endpoint: str, params: dict) -> dict:
    if not KEY:
        raise RuntimeError("API_FOOTBALL_KEY is not configured")
    cfg = SPORTS[sport]
    r = requests.get(
        f"{cfg['base']}/{endpoint.lstrip('/')}",
        params=params,
        headers={"x-apisports-key": KEY, "Accept": "application/json", "User-Agent": UA},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data


def _team_name(item: dict, side: str) -> str | None:
    teams = item.get("teams") or {}
    obj = teams.get(side) or {}
    return obj.get("name")


def discover(sport: str, day: str) -> list[dict]:
    data = api_get(sport, SPORTS[sport]["endpoint"], {"date": day})
    out = []
    for item in data.get("response") or []:
        home = _team_name(item, "home")
        away = _team_name(item, "away")
        if not home or not away:
            continue
        fixture = item.get("fixture") or item.get("game") or {}
        status = (fixture.get("status") or {}).get("short") or (fixture.get("status") or {}).get("long")
        if isinstance(status, str) and status.lower() in {"ft", "finished", "final", "aet", "pen", "canceled", "cancelled", "postponed"}:
            continue
        league = item.get("league") or {}
        out.append({
            "sport": sport,
            "home": home,
            "away": away,
            "home_id": ((item.get("teams") or {}).get("home") or {}).get("id"),
            "away_id": ((item.get("teams") or {}).get("away") or {}).get("id"),
            "league": league.get("name"),
            "league_id": league.get("id"),
            "fixture_id": fixture.get("id") or fixture.get("game_id"),
            "status": status,
        })
    return out


def _odd(value) -> float | None:
    try:
        x = float(value)
        return x if x > 1.0 else None
    except (TypeError, ValueError):
        return None


def get_odds(match: dict) -> list[dict]:
    """Return normalized winner/moneyline odds from API-Sports bookmakers."""
    fixture_id = match.get("fixture_id")
    if not fixture_id:
        return []
    cfg = SPORTS[match["sport"]]
    try:
        data = api_get(match["sport"], cfg["odds"], {cfg["id_key"]: fixture_id})
    except Exception as exc:
        print(f"odds failed {match['sport']} {fixture_id}: {type(exc).__name__}: {exc}")
        return []

    out: list[dict] = []
    for bookmaker in data.get("response") or []:
        bookmaker_name = bookmaker.get("bookmaker", {}).get("name") or bookmaker.get("name") or "unknown"
        for bet in bookmaker.get("bets") or []:
            bet_name = str(bet.get("name") or "").lower()
            # Winner / moneyline is the cleanest cross-sport market.
            if not any(k in bet_name for k in ("winner", "moneyline", "match winner", "match")):
                continue
            for value in bet.get("values") or []:
                label = value.get("value") or value.get("name")
                odd = _odd(value.get("odd"))
                if label and odd:
                    out.append({"bookmaker": bookmaker_name, "market": bet.get("name"), "label": str(label), "odd": odd})
            if out and len(out) >= 12:
                break
        if len(out) >= 12:
            break
    return out


def attach_market(match: dict) -> dict:
    odds = get_odds(match)
    if not odds:
        return {**match, "odds": [], "evidence": "NO_ODDS"}
    # Keep the best available price per outcome label.
    best: dict[str, dict] = {}
    for row in odds:
        key = row["label"].strip().lower()
        if key not in best or row["odd"] > best[key]["odd"]:
            best[key] = row
    market = sorted(best.values(), key=lambda x: x["odd"])
    return {**match, "odds": market, "evidence": "ODDS_AVAILABLE"}


def _is_home_label(label: str, match: dict) -> bool:
    s = label.strip().lower()
    return s in {match["home"].strip().lower(), "home", "1", "team 1"}


def score_market(match: dict) -> list[dict]:
    """Convert real odds into market-implied candidates; no fabricated model score."""
    rows = []
    for row in match.get("odds", []):
        odd = row["odd"]
        implied = 1.0 / odd
        # Broad sanity band: avoid extreme novelty prices and obvious feed errors.
        if 1.20 <= odd <= 8.00:
            side = match["home"] if _is_home_label(row["label"], match) else match["away"]
            rows.append({
                "sport": match["sport"], "home": match["home"], "away": match["away"],
                "league": match.get("league"), "fixture_id": match.get("fixture_id"),
                "pick": side, "market": row.get("market"), "odd": round(odd, 2),
                "implied_probability": round(implied, 4), "bookmaker": row.get("bookmaker"),
            })
    return rows


def build_coupons(fixtures: list[dict]) -> dict:
    candidates: list[dict] = []
    for match in fixtures:
        enriched = attach_market(match)
        candidates.extend(score_market(enriched))

    # Deduplicate by fixture + pick and keep the highest available price.
    best: dict[tuple, dict] = {}
    for c in candidates:
        key = (c["sport"], c["fixture_id"], c["pick"])
        if key not in best or c["odd"] > best[key]["odd"]:
            best[key] = c
    candidates = list(best.values())

    # Conservative: strongest market probability, with sport diversity.
    conservative: list[dict] = []
    used_sports: set[str] = set()
    for c in sorted(candidates, key=lambda x: (-x["implied_probability"], x["odd"])):
        if c["sport"] not in used_sports:
            conservative.append({**c, "risk": "medium"})
            used_sports.add(c["sport"])
        if len(conservative) >= 4:
            break
    if len(conservative) < 3:
        for c in sorted(candidates, key=lambda x: (-x["implied_probability"], x["odd"])):
            if c not in conservative:
                conservative.append({**c, "risk": "medium-high"})
            if len(conservative) >= 4:
                break

    # Surprise: higher odds, but still capped at 8.00 to avoid lottery picks.
    surprise: list[dict] = []
    for c in sorted(candidates, key=lambda x: (-x["odd"], -x["implied_probability"])):
        if c not in conservative:
            surprise.append({**c, "risk": "high"})
        if len(surprise) >= 4:
            break

    return {
        "conservative_mixed": conservative,
        "surprise_mixed": surprise,
        "eligible_candidates": len(candidates),
        "disclaimer": "Selections are market-based because the free API plan does not reliably expose historical form for every current fixture. No pick is guaranteed; check final odds/lineups before staking.",
    }


def main() -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = {"date_utc": day, "api_key_configured": bool(KEY), "fixtures_by_sport": {}, "odds_available_by_sport": {}, "errors": {}, "coupons": {}}
    if not KEY:
        raise SystemExit("API_FOOTBALL_KEY is not configured")

    # Limit fixture discovery to keep the free quota under control.
    all_fixtures: list[dict] = []
    for sport in SPORTS:
        try:
            fixtures = discover(sport, day)[:6]
            report["fixtures_by_sport"][sport] = len(fixtures)
            all_fixtures.extend(fixtures)
            print(f"{sport}: {len(fixtures)} upcoming fixtures")
        except Exception as exc:
            report["fixtures_by_sport"][sport] = 0
            report["errors"][sport] = f"{type(exc).__name__}: {exc}"
            print(f"{sport}: FAILED {type(exc).__name__}: {exc}")

    # Query odds only for the selected small pool.
    enriched = []
    for match in all_fixtures:
        item = attach_market(match)
        if item["evidence"] == "ODDS_AVAILABLE":
            report["odds_available_by_sport"][match["sport"]] = report["odds_available_by_sport"].get(match["sport"], 0) + 1
        enriched.append(item)

    report["coupons"] = build_coupons(enriched)
    if not report["coupons"]["conservative_mixed"] and not report["coupons"]["surprise_mixed"]:
        report["coupons"]["status"] = "NO_BET"
        report["coupons"]["reason"] = "No current fixture had usable bookmaker odds from API-Sports. No artificial picks were generated."
    else:
        report["coupons"]["status"] = "READY_FOR_MANUAL_CHECK"

    out = Path("reports/multi_sport_coupon.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date_utc": day, "fixtures_by_sport": report["fixtures_by_sport"], "odds_available_by_sport": report["odds_available_by_sport"], "status": report["coupons"]["status"], "conservative": report["coupons"]["conservative_mixed"], "surprise": report["coupons"]["surprise_mixed"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
