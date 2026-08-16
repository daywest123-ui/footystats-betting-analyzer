"""Discover fixtures and rank them with form + public-web evidence.

This module is a ranking/analysis layer only. It does not place bets.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from open_web_intelligence import analyze_match
from signal_fusion import fuse

TIMEOUT = 20
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
BBC_URL = "https://www.bbc.co.uk/sport/football/scores-fixtures"
SPORTSDB_API = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php"
SPORTSDB_LAST = "https://www.thesportsdb.com/api/v1/json/123/eventslast.php"
SOFASCORE_API = "https://www.sofascore.com/api/v1/sport/football/scheduled-events"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard"


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _bbc_fixtures(date: datetime) -> list[dict]:
    url = f"{BBC_URL}/{date:%Y-%m-%d}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT)
    r.raise_for_status()
    teams: list[str] = []
    seen: set[str] = set()
    patterns = [
        r'<span[^>]*class="[^"]*qa-full-team-name[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*class="[^"]*sp-c-fixture__team-name-trunc[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*data-testid="[^\"]*team[^\"]*"[^>]*>(.*?)</span>',
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, r.text, flags=re.I | re.S):
            name = _clean_html_text(raw)
            if name and len(name) < 80 and name.lower() not in seen:
                seen.add(name.lower())
                teams.append(name)
    return [{"home": teams[i].strip(), "away": teams[i + 1].strip()} for i in range(0, len(teams) - 1, 2)]


def _sportsdb_fixtures(date: datetime) -> list[dict]:
    r = requests.get(SPORTSDB_API, params={"d": date.strftime("%Y-%m-%d"), "s": "Soccer"}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    fixtures = []
    seen = set()
    for event in r.json().get("events") or []:
        home, away = event.get("strHomeTeam"), event.get("strAwayTeam")
        if not home or not away or home.strip().lower() == away.strip().lower():
            continue
        key = (home.strip(), away.strip())
        if key in seen:
            continue
        seen.add(key)
        fixtures.append({
            "home": key[0], "away": key[1],
            "home_id": event.get("idHomeTeam"), "away_id": event.get("idAwayTeam"),
            "league": event.get("strLeague"), "fixture_date": event.get("dateEvent"),
        })
    return fixtures


def _sofascore_fixtures(date: datetime) -> list[dict]:
    r = requests.get(f"{SOFASCORE_API}/{date:%Y-%m-%d}", headers={"User-Agent": UA, "Accept": "application/json", "Referer": "https://www.sofascore.com/"}, timeout=TIMEOUT)
    r.raise_for_status()
    fixtures, seen = [], set()
    for event in r.json().get("events", []):
        status = (event.get("status") or {}).get("type", "")
        if status not in {"notstarted", "postponed", "canceled"}:
            continue
        home = (event.get("homeTeam") or {}).get("name")
        away = (event.get("awayTeam") or {}).get("name")
        if not home or not away:
            continue
        key = (home.strip(), away.strip())
        if key not in seen:
            seen.add(key)
            fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def _api_fixtures(date: datetime) -> list[dict]:
    r = requests.get(ESPN_API, params={"dates": date.strftime("%Y%m%d")}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    fixtures, seen = [], set()
    for event in r.json().get("events", []):
        for competition in event.get("competitions") or []:
            competitors = competition.get("competitors") or []
            home = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "away"), None)
            if home and away:
                key = (home.strip(), away.strip())
                if key not in seen:
                    seen.add(key)
                    fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def discover_fixtures(date: datetime) -> list[dict]:
    for label, loader in [("BBC", _bbc_fixtures), ("TheSportsDB", _sportsdb_fixtures), ("Sofascore", _sofascore_fixtures), ("ESPN API", _api_fixtures)]:
        try:
            fixtures = loader(date)
            print(f"{label} fixture discovery: {len(fixtures)} fixtures")
            if fixtures:
                return fixtures[:30]
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"{label} discovery failed: {type(exc).__name__}: {exc}")
    return []


def _recent_form(team_id: str | None) -> dict:
    """Return compact last-results features from TheSportsDB, when team ID is available."""
    if not team_id:
        return {"matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0, "over25_rate": 0.5, "btts_rate": 0.5}
    try:
        r = requests.get(SPORTSDB_LAST, params={"id": team_id}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
        r.raise_for_status()
        events = [e for e in (r.json().get("results") or []) if e.get("intHomeScore") is not None and e.get("intAwayScore") is not None][:8]
        if not events:
            return {"matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0, "over25_rate": 0.5, "btts_rate": 0.5}
        pts = gd = over25 = btts = 0.0
        for e in events:
            hs, aw = int(e["intHomeScore"]), int(e["intAwayScore"])
            is_home = str(e.get("idHomeTeam")) == str(team_id)
            gf, ga = (hs, aw) if is_home else (aw, hs)
            pts += 3 if gf > ga else 1 if gf == ga else 0
            gd += gf - ga
            over25 += int(hs + aw >= 3)
            btts += int(hs > 0 and aw > 0)
        n = len(events)
        return {"matches": n, "points_per_game": pts / n, "goal_diff_per_game": gd / n, "over25_rate": over25 / n, "btts_rate": btts / n}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {"matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0, "over25_rate": 0.5, "btts_rate": 0.5}


def _stat_probability(home_form: dict, away_form: dict) -> float:
    """Calibrated heuristic from recent form; deliberately capped to avoid fake certainty."""
    h_ppg = home_form["points_per_game"]
    a_ppg = away_form["points_per_game"]
    form_edge = max(-1.0, min(1.0, (h_ppg - a_ppg) / 3.0))
    gd_edge = max(-1.0, min(1.0, (home_form["goal_diff_per_game"] - away_form["goal_diff_per_game"]) / 3.0))
    home_advantage = 0.04
    raw = 0.50 + 0.18 * form_edge + 0.12 * gd_edge + home_advantage
    return max(0.38, min(0.68, raw))


def score_fixture(fixture: dict) -> dict:
    home_form = _recent_form(fixture.get("home_id"))
    away_form = _recent_form(fixture.get("away_id"))
    stat_probability = _stat_probability(home_form, away_form)
    intel = analyze_match(fixture["home"], fixture["away"])
    web_score = float(intel.get("web_score", 0.0))
    confidence = float(intel.get("confidence", 0.0))
    fused = fuse(stat_probability, web_score, confidence)
    return {**fixture, "form": {"home": home_form, "away": away_form}, "intelligence": intel, "signal": fused}


def main() -> None:
    now = datetime.now(timezone.utc)
    fixtures = discover_fixtures(now)
    print(f"Total fixtures selected for analysis: {len(fixtures)}")
    results = [score_fixture(f) for f in fixtures]
    results.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)
    report = {
        "generated_at": now.isoformat(),
        "mode": "automatic_selection_form_web_no_bet",
        "fixtures_scanned": len(results),
        "model_notes": "Recent form + goal-difference heuristic fused with capped public-web evidence; probability is a ranking signal, not a guarantee.",
        "top_matches": results[:5],
    }
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for n, item in enumerate(results[:5], 1):
        s = item["signal"]
        print(f"#{n} {item['home']} - {item['away']} | {s['category']} | probability={s['final_probability']:.1%} | form={item['form']['home']['points_per_game']:.2f}/{item['form']['away']['points_per_game']:.2f} | web={item['intelligence']['mentions']} mentions")


if __name__ == "__main__":
    main()
