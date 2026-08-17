"""Multi-sport coupon scanner using the existing API-Sports key.

This module is deliberately analysis-only: it never places bets. It discovers
same-day fixtures across supported API-Sports products and produces two
shortlists: a conservative mixed coupon and a higher-variance surprise coupon.
Because the free plan can restrict historical seasons/competitions, the first
version only scores fixtures for which the API exposes enough current data.
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
    "football": {"base": "https://v3.football.api-sports.io", "endpoint": "fixtures", "home": ("teams", "home", "name"), "away": ("teams", "away", "name")},
    "basketball": {"base": "https://v1.basketball.api-sports.io", "endpoint": "games", "home": ("teams", "home", "name"), "away": ("teams", "away", "name")},
    "volleyball": {"base": "https://v1.volleyball.api-sports.io", "endpoint": "games", "home": ("teams", "home", "name"), "away": ("teams", "away", "name")},
    "hockey": {"base": "https://v1.hockey.api-sports.io", "endpoint": "games", "home": ("teams", "home", "name"), "away": ("teams", "away", "name")},
}


def api_get(sport: str, params: dict) -> dict:
    if not KEY:
        raise RuntimeError("API_FOOTBALL_KEY is not configured")
    cfg = SPORTS[sport]
    r = requests.get(
        f"{cfg['base']}/{cfg['endpoint']}",
        params=params,
        headers={"x-apisports-key": KEY, "Accept": "application/json", "User-Agent": UA},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data


def nested_name(obj: dict, path: tuple[str, str, str]) -> str | None:
    a = obj.get(path[0]) or {}
    b = a.get(path[1]) or {}
    return b.get(path[2])


def discover(sport: str, day: str) -> list[dict]:
    data = api_get(sport, {"date": day})
    out = []
    for item in data.get("response") or []:
        cfg = SPORTS[sport]
        home = nested_name(item, cfg["home"])
        away = nested_name(item, cfg["away"])
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
            "league": league.get("name"),
            "league_id": league.get("id"),
            "fixture_id": fixture.get("id") or fixture.get("game_id"),
            "status": status,
            "raw": item,
        })
    return out


def pick_score(match: dict) -> tuple[float, str]:
    # Without reliable odds/history, score only structural information. This
    # prevents the generator from pretending it has certainty it does not have.
    sport = match["sport"]
    league = (match.get("league") or "").lower()
    score = 0.50
    reason = "API fixture confirmed; insufficient historical edge for a strong side pick"
    if sport == "football":
        score = 0.54
        reason = "Football fixture selected for the mixed pool; form/odds must be checked before staking"
    elif sport == "basketball":
        score = 0.56
        reason = "Basketball fixture selected; winner market is more suitable than goal-based markets"
    elif sport == "volleyball":
        score = 0.55
        reason = "Volleyball fixture selected; match-winner market is the natural market"
    elif sport == "hockey":
        score = 0.53
        reason = "Hockey fixture selected; moneyline/winner market is the natural market"
    if any(x in league for x in ("world", "champions", "europe")):
        score += 0.01
    return min(score, 0.60), reason


def build_coupons(fixtures: list[dict]) -> dict:
    scored = []
    for m in fixtures:
        score, reason = pick_score(m)
        scored.append({**{k: m[k] for k in ("sport", "home", "away", "league", "fixture_id")}, "score": round(score, 3), "reason": reason})
    scored.sort(key=lambda x: (-x["score"], x["sport"], x["home"]))
    # Prefer diversity: one pick per sport before adding a second football/basketball pick.
    conservative = []
    for sport in ("football", "basketball", "volleyball", "hockey"):
        item = next((x for x in scored if x["sport"] == sport), None)
        if item:
            conservative.append({**item, "risk": "medium"})
    if len(conservative) < 3:
        for item in scored:
            if item not in conservative:
                conservative.append({**item, "risk": "medium-high"})
            if len(conservative) >= 4:
                break
    surprise = []
    for item in reversed(scored):
        if item not in conservative or item["sport"] in {"football", "hockey"}:
            surprise.append({**item, "risk": "high"})
        if len(surprise) >= 4:
            break
    return {"conservative_mixed": conservative[:4], "surprise_mixed": surprise[:4], "disclaimer": "No pick is guaranteed. This first multi-sport pass is API-driven fixture selection; do not stake until live odds and final lineups are checked."}


def main() -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = {"date_utc": day, "api_key_configured": bool(KEY), "fixtures_by_sport": {}, "errors": {}, "coupons": {}}
    if not KEY:
        raise SystemExit("API_FOOTBALL_KEY is not configured")
    all_fixtures = []
    for sport in SPORTS:
        try:
            fixtures = discover(sport, day)
            report["fixtures_by_sport"][sport] = len(fixtures)
            all_fixtures.extend(fixtures)
            print(f"{sport}: {len(fixtures)} upcoming fixtures")
        except Exception as exc:
            report["fixtures_by_sport"][sport] = 0
            report["errors"][sport] = f"{type(exc).__name__}: {exc}"
            print(f"{sport}: FAILED {type(exc).__name__}: {exc}")
    report["coupons"] = build_coupons(all_fixtures)
    out = Path("reports/multi_sport_coupon.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date_utc": day, "fixtures_by_sport": report["fixtures_by_sport"], "conservative": report["coupons"]["conservative_mixed"], "surprise": report["coupons"]["surprise_mixed"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
