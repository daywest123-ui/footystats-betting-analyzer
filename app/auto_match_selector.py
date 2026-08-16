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
SPORTSDB_SEASON = "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php"
SOFASCORE_API = "https://www.sofascore.com/api/v1/sport/football/scheduled-events"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard"


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _bbc_fixtures(date: datetime) -> list[dict]:
    url = f"{BBC_URL}/{date:%Y-%m-%d}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT)
    r.raise_for_status()
    teams: list[str] = []
    seen: set[str] = set()
    patterns = [
        r'<span[^>]*class="[^\"]*qa-full-team-name[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*class="[^\"]*sp-c-fixture__team-name-trunc[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*data-testid="[^\"]*team[^\"]*"[^>]*>(.*?)</span>',
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, r.text, flags=re.I | re.S):
            name = _clean_html_text(raw)
            if name and len(name) < 80 and name.lower() not in seen:
                seen.add(name.lower())
                teams.append(name)
    return [{"home": teams[i], "away": teams[i + 1]} for i in range(0, len(teams) - 1, 2)]


def _sportsdb_fixtures(date: datetime) -> list[dict]:
    r = requests.get(SPORTSDB_API, params={"d": date.strftime("%Y-%m-%d"), "s": "Soccer"}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    fixtures, seen = [], set()
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


def _empty_form() -> dict:
    return {"matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0, "over25_rate": 0.5, "btts_rate": 0.5}


def _score_events(team_id: str, events: list[dict], limit: int = 8) -> dict:
    completed = []
    for e in events:
        hs_raw, aw_raw = e.get("intHomeScore"), e.get("intAwayScore")
        if hs_raw is None or aw_raw is None:
            continue
        try:
            hs, aw = int(hs_raw), int(aw_raw)
        except (TypeError, ValueError):
            continue
        date_raw = e.get("dateEvent") or e.get("strTimestamp") or ""
        try:
            event_date = str(date_raw)[:10]
            if event_date and event_date > datetime.now(timezone.utc).date().isoformat():
                continue
        except Exception:
            pass
        completed.append((e, hs, aw))
    completed.sort(key=lambda x: str(x[0].get("dateEvent") or x[0].get("strTimestamp") or ""), reverse=True)
    completed = completed[:limit]
    if not completed:
        return _empty_form()
    pts = gd = over25 = btts = 0.0
    for e, hs, aw in completed:
        is_home = str(e.get("idHomeTeam")) == str(team_id)
        gf, ga = (hs, aw) if is_home else (aw, hs)
        pts += 3 if gf > ga else 1 if gf == ga else 0
        gd += gf - ga
        over25 += int(hs + aw >= 3)
        btts += int(hs > 0 and aw > 0)
    n = len(completed)
    return {"matches": n, "points_per_game": pts / n, "goal_diff_per_game": gd / n, "over25_rate": over25 / n, "btts_rate": btts / n}


def _recent_form(team_id: str | None) -> dict:
    """Return up to eight recent completed results.

    TheSportsDB's eventslast endpoint is useful but can be sparse for some teams.
    When it returns fewer than five usable matches, fall back to the current and
    previous season event lists for the same team and merge/deduplicate them.
    """
    if not team_id:
        return _empty_form()
    try:
        r = requests.get(SPORTSDB_LAST, params={"id": team_id}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
        r.raise_for_status()
        last_events = r.json().get("results") or []
        quick = _score_events(str(team_id), last_events, 8)
        if quick["matches"] >= 5:
            return quick

        now = datetime.now(timezone.utc)
        season_candidates = [f"{now.year}-{now.year + 1}", f"{now.year - 1}-{now.year}", f"{now.year - 2}-{now.year - 1}"]
        merged: dict[str, dict] = {}
        for season in season_candidates:
            try:
                sr = requests.get(SPORTSDB_SEASON, params={"id": team_id, "s": season}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
                sr.raise_for_status()
                for event in sr.json().get("events") or []:
                    event_id = str(event.get("idEvent") or f"{event.get('dateEvent')}|{event.get('strHomeTeam')}|{event.get('strAwayTeam')}")
                    merged[event_id] = event
            except (requests.RequestException, ValueError, KeyError, TypeError):
                continue
            if len(merged) >= 12:
                break
        # Include the fast endpoint too; season feeds occasionally omit a match.
        for event in last_events:
            event_id = str(event.get("idEvent") or f"{event.get('dateEvent')}|{event.get('strHomeTeam')}|{event.get('strAwayTeam')}")
            merged[event_id] = event
        return _score_events(str(team_id), list(merged.values()), 8)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return _empty_form()


def _stat_probability(home_form: dict, away_form: dict) -> float:
    """Blend form signals, then cap based on sample size to avoid false certainty."""
    h_ppg, a_ppg = home_form["points_per_game"], away_form["points_per_game"]
    form_edge = max(-1.0, min(1.0, (h_ppg - a_ppg) / 3.0))
    gd_edge = max(-1.0, min(1.0, (home_form["goal_diff_per_game"] - away_form["goal_diff_per_game"]) / 3.0))
    totals_edge = ((home_form["over25_rate"] + away_form["over25_rate"]) / 2.0) - 0.5
    btts_edge = ((home_form["btts_rate"] + away_form["btts_rate"]) / 2.0) - 0.5
    raw = 0.50 + 0.16 * form_edge + 0.10 * gd_edge + 0.03 * totals_edge + 0.03 * btts_edge + 0.04
    n = min(home_form["matches"], away_form["matches"])
    cap = 0.50 if n < 3 else 0.55 if n < 5 else 0.62 if n < 8 else 0.68
    floor = 1.0 - cap
    return max(floor, min(cap, raw))


def score_fixture(fixture: dict) -> dict:
    home_form = _recent_form(fixture.get("home_id"))
    away_form = _recent_form(fixture.get("away_id"))
    min_matches = min(home_form["matches"], away_form["matches"])
    stat_probability = _stat_probability(home_form, away_form)
    intel = analyze_match(fixture["home"], fixture["away"])
    web_score = float(intel.get("web_score", 0.0))
    confidence = float(intel.get("confidence", 0.0))
    fused = fuse(stat_probability, web_score, confidence)
    if min_matches < 3:
        status = "INSUFFICIENT_DATA"
        fused["final_probability"] = 0.5
        fused["category"] = "AVOID"
    elif min_matches < 5:
        status = "LOW_SAMPLE"
        fused["final_probability"] = min(0.55, max(0.45, float(fused.get("final_probability", 0.5))))
    elif min_matches < 8:
        status = "MEDIUM_SAMPLE"
        fused["final_probability"] = min(0.62, max(0.38, float(fused.get("final_probability", 0.5))))
    else:
        status = "FULL_SAMPLE"
        fused["final_probability"] = min(0.68, max(0.32, float(fused.get("final_probability", 0.5))))
    return {**fixture, "data_quality": {"min_recent_matches": min_matches, "status": status}, "form": {"home": home_form, "away": away_form}, "intelligence": intel, "signal": fused}


def main() -> None:
    now = datetime.now(timezone.utc)
    fixtures = discover_fixtures(now)
    print(f"Total fixtures selected for analysis: {len(fixtures)}")
    results = [score_fixture(f) for f in fixtures]
    eligible = [r for r in results if r["data_quality"]["min_recent_matches"] >= 5]
    eligible.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)
    results.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)
    print(f"Eligible matches (>=5 recent matches per team): {len(eligible)}")
    report = {
        "generated_at": now.isoformat(),
        "mode": "automatic_selection_form_web_calibrated_no_bet",
        "fixtures_scanned": len(results),
        "eligible_matches": len(eligible),
        "model_notes": "Form + goal difference + Over2.5/BTTS heuristics fused with public-web evidence. Minimum 5 recent matches required for an eligible signal; probabilities are capped by sample size and are not guarantees.",
        "top_matches": eligible[:5],
        "all_scanned": results[:30],
    }
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for n, item in enumerate(eligible[:5], 1):
        s = item["signal"]
        print(f"#{n} {item['home']} - {item['away']} | {s['category']} | probability={s['final_probability']:.1%} | sample={item['data_quality']['min_recent_matches']} | form={item['form']['home']['points_per_game']:.2f}/{item['form']['away']['points_per_game']:.2f} | web={item['intelligence']['mentions']} mentions")
    if not eligible:
        print("NO BET: no match has at least 5 recent completed matches for both teams.")


if __name__ == "__main__":
    main()
