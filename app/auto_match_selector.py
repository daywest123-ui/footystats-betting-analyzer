"""Automatically discover public football fixtures, score public-web evidence, and select candidates.

No paid API is used and no bet is placed. Fixture discovery uses BBC's public
scores/fixtures page first, then TheSportsDB/Sofascore/ESPN fallbacks; match
intelligence uses public Google News RSS feeds in Turkish and English.
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
SOFASCORE_API = "https://www.sofascore.com/api/v1/sport/football/scheduled-events"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard"


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\\s+", " ", value).strip()
    return value


def _bbc_fixtures(date: datetime) -> list[dict]:
    """Scrape BBC's static scores/fixtures page using its stable fixture classes."""
    url = f"{BBC_URL}/{date:%Y-%m-%d}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text

    # BBC has historically exposed full team names in spans with this class.
    patterns = [
        r'<span[^>]*class="[^"]*qa-full-team-name[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*class="[^"]*sp-c-fixture__team-name-trunc[^\"]*"[^>]*>(.*?)</span>',
        r'<span[^>]*data-testid="[^\"]*team[^\"]*"[^>]*>(.*?)</span>',
    ]
    teams: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I | re.S):
            name = _clean_html_text(raw)
            if name and len(name) < 80 and name.lower() not in seen:
                seen.add(name.lower())
                teams.append(name)

    fixtures = []
    for i in range(0, len(teams) - 1, 2):
        home, away = teams[i].strip(), teams[i + 1].strip()
        if home.lower() != away.lower():
            fixtures.append({"home": home, "away": away})
    return fixtures[:30]


def _sportsdb_fixtures(date: datetime) -> list[dict]:
    r = requests.get(
        SPORTSDB_API,
        params={"d": date.strftime("%Y-%m-%d"), "s": "Soccer"},
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    fixtures: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in data.get("events") or []:
        home, away = event.get("strHomeTeam"), event.get("strAwayTeam")
        if not home or not away or home.strip().lower() == away.strip().lower():
            continue
        key = (home.strip(), away.strip())
        if key not in seen:
            seen.add(key)
            fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def _sofascore_fixtures(date: datetime) -> list[dict]:
    url = f"{SOFASCORE_API}/{date:%Y-%m-%d}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json", "Referer": "https://www.sofascore.com/"}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    fixtures, seen = [], set()
    for event in data.get("events", []):
        status = (event.get("status") or {}).get("type", "")
        if status not in {"notstarted", "postponed", "canceled"}:
            continue
        home = (event.get("homeTeam") or {}).get("name")
        away = (event.get("awayTeam") or {}).get("name")
        if not home or not away or home.strip().lower() == away.strip().lower():
            continue
        key = (home.strip(), away.strip())
        if key not in seen:
            seen.add(key)
            fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def _api_fixtures(date: datetime) -> list[dict]:
    r = requests.get(ESPN_API, params={"dates": date.strftime("%Y%m%d")}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    fixtures, seen = [], set()
    for event in data.get("events", []):
        for competition in event.get("competitions") or []:
            competitors = competition.get("competitors") or []
            home = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            key = (home.strip(), away.strip())
            if key not in seen:
                seen.add(key)
                fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def discover_fixtures(date: datetime) -> list[dict]:
    sources = [
        ("BBC", _bbc_fixtures),
        ("TheSportsDB", _sportsdb_fixtures),
        ("Sofascore", _sofascore_fixtures),
        ("ESPN API", _api_fixtures),
    ]
    for label, loader in sources:
        try:
            fixtures = loader(date)
            print(f"{label} fixture discovery: {len(fixtures)} fixtures")
            if fixtures:
                return fixtures[:30]
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"{label} discovery failed: {type(exc).__name__}: {exc}")
    return []


def score_fixture(fixture: dict) -> dict:
    intel = analyze_match(fixture["home"], fixture["away"])
    web_score = float(intel.get("web_score", 0.0))
    confidence = float(intel.get("confidence", 0.0))
    stat_proxy = 0.50 + 0.20 * web_score
    fused = fuse(stat_proxy, web_score, confidence)
    return {**fixture, "intelligence": intel, "signal": fused}


def main() -> None:
    now = datetime.now(timezone.utc)
    fixtures = discover_fixtures(now)
    print(f"Total fixtures selected for analysis: {len(fixtures)}")
    results = [score_fixture(f) for f in fixtures]
    results.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)
    report = {
        "generated_at": now.isoformat(),
        "mode": "automatic_selection_no_email_no_bet",
        "fixtures_scanned": len(results),
        "top_matches": results[:5],
    }
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for n, item in enumerate(results[:5], 1):
        s = item["signal"]
        print(f"#{n} {item['home']} - {item['away']} | {s['category']} | probability={s['final_probability']:.1%} | web={item['intelligence']['mentions']} mentions")


if __name__ == "__main__":
    main()
