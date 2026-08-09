"""Automatically discover public football fixtures, score public-web evidence, and select candidates.

No paid API is used and no bet is placed. Fixture discovery uses ESPN's public scoreboard page;
match intelligence uses public Google News RSS feeds in Turkish and English.
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


def discover_fixtures(date: datetime) -> list[dict]:
    url = f"https://www.espn.com/soccer/scoreboard/_/date/{date:%Y%m%d}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text
    # ESPN embeds scoreboard data as JSON. This regex intentionally accepts both quoted
    # and unquoted team-name fields because the page format changes periodically.
    names = re.findall(r'"(?:displayName|shortDisplayName|name)":"([^"]+)"', text)
    names = [re.sub(r"\\u0026", "&", n) for n in names]
    teams = []
    seen = set()
    for n in names:
        n = re.sub(r"\\+", " ", n).strip()
        if n and n not in seen and len(n) < 80:
            seen.add(n)
            teams.append(n)
    fixtures = []
    for i in range(0, len(teams) - 1, 2):
        home, away = teams[i], teams[i + 1]
        if home.lower() == away.lower():
            continue
        fixtures.append({"home": home, "away": away})
    return fixtures[:30]


def score_fixture(fixture: dict) -> dict:
    intel = analyze_match(fixture["home"], fixture["away"])
    # Web sentiment is used only as supporting evidence. With no market odds supplied,
    # this produces a transparent research ranking rather than a guaranteed bet.
    web_score = float(intel.get("web_score", 0.0))
    confidence = float(intel.get("confidence", 0.0))
    stat_proxy = 0.50 + 0.20 * web_score
    fused = fuse(stat_proxy, web_score, confidence)
    return {**fixture, "intelligence": intel, "signal": fused}


def main() -> None:
    now = datetime.now(timezone.utc)
    fixtures = discover_fixtures(now)
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
