"""Automatically discover public football fixtures, score public-web evidence, and select candidates.

No paid API is used and no bet is placed. Fixture discovery uses ESPN's public scoreboard
API first and falls back to the public scoreboard page; match intelligence uses public
Google News RSS feeds in Turkish and English.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from open_web_intelligence import analyze_match
from signal_fusion import fuse

TIMEOUT = 20
UA = "Mozilla/5.0 (compatible; FootballAnalyzer/1.0)"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard"


def _api_fixtures(date: datetime) -> list[dict]:
    """Read fixtures from ESPN's public JSON scoreboard endpoint."""
    r = requests.get(
        ESPN_API,
        params={"dates": date.strftime("%Y%m%d")},
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    fixtures: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for event in data.get("events", []):
        competitions = event.get("competitions") or []
        for competition in competitions:
            competitors = competition.get("competitors") or []
            home = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c.get("team", {}).get("displayName") for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away or home.strip().lower() == away.strip().lower():
                continue
            key = (home.strip(), away.strip())
            if key not in seen:
                seen.add(key)
                fixtures.append({"home": key[0], "away": key[1]})
    return fixtures


def _html_fixtures(date: datetime) -> list[dict]:
    """Fallback parser for ESPN's rendered scoreboard page."""
    url = f"https://www.espn.com/soccer/scoreboard/_/date/{date:%Y%m%d}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text

    patterns = [
        r'"(?:displayName|shortDisplayName|name)"\s*:\s*"([^"]+)"',
        r'"team"\s*:\s*\{[^{}]*"(?:displayName|shortDisplayName|name)"\s*:\s*"([^"]+)"',
    ]
    names: list[str] = []
    for pattern in patterns:
        names.extend(re.findall(pattern, text))

    teams: list[str] = []
    seen: set[str] = set()
    for name in names:
        name = name.replace("\\u0026", "&")
        name = name.replace("\\u0027", "'")
        name = re.sub(r"\\+", " ", name).strip()
        if name and name not in seen and len(name) < 80:
            seen.add(name)
            teams.append(name)

    return [
        {"home": teams[i], "away": teams[i + 1]}
        for i in range(0, len(teams) - 1, 2)
        if teams[i].lower() != teams[i + 1].lower()
    ][:30]


def discover_fixtures(date: datetime) -> list[dict]:
    """Discover today's fixtures, preferring structured JSON over fragile HTML scraping."""
    try:
        fixtures = _api_fixtures(date)
        print(f"ESPN API fixture discovery: {len(fixtures)} fixtures")
        if fixtures:
            return fixtures[:30]
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"ESPN API discovery failed: {type(exc).__name__}: {exc}")

    try:
        fixtures = _html_fixtures(date)
        print(f"ESPN HTML fixture discovery fallback: {len(fixtures)} fixtures")
        return fixtures[:30]
    except requests.RequestException as exc:
        print(f"ESPN HTML discovery failed: {type(exc).__name__}: {exc}")
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
    (out / "latest_auto_analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for n, item in enumerate(results[:5], 1):
        s = item["signal"]
        print(
            f"#{n} {item['home']} - {item['away']} | {s['category']} | "
            f"probability={s['final_probability']:.1%} | "
            f"web={item['intelligence']['mentions']} mentions"
        )


if __name__ == "__main__":
    main()
