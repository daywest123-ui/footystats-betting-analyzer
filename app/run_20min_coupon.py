"""20-minute football coupon pipeline.

Analysis/paper-selection only. It never places bets.
Uses same-day verified odds from football-data.co.uk and refuses stale or
missing prices when current odds cannot be obtained.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from app.football_data_client import load_openfootball, recent_form, fixture_odds
from app.open_web_intelligence import analyze_match
from app.odds_pipeline import analyze_fixture_markets, _devig_probability
from app.auto_match_selector import _market_probabilities

MAX_WEB_FIXTURES = 6
MAX_COUPON_LEGS = 4
MIN_RECENT_MATCHES = 5
MIN_VALUE_EDGE = 0.025
MAX_RUNTIME_SECONDS = 17 * 60
LOCAL_TZ = ZoneInfo("Europe/Istanbul")


def _remaining(started: float) -> float:
    return MAX_RUNTIME_SECONDS - (time.monotonic() - started)


def run():
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    day = now.astimezone(LOCAL_TZ).date().isoformat()
    report = {
        "generated_at": now.isoformat(),
        "target_date": day,
        "local_timezone": "Europe/Istanbul",
        "pipeline": "20MIN_V4",
        "run_status": "STARTED",
        "decision_status": "NO_BET",
        "stages": {},
        "coupon": [],
        "rejected": [],
    }

    print("=== 20-MIN FOOTBALL COUPON ENGINE ===")
    print(f"Target date: {day}")

    matches = load_openfootball()
    fixtures = []
    for m in matches:
        if _remaining(started) <= 0:
            report["stages"]["deadline"] = "reached_during_fixture_scan"
            break
        if m.get("date") != day or m.get("finished"):
            continue

        home_form = recent_form(matches, m["home"], day, 8)
        away_form = recent_form(matches, m["away"], day, 8)
        sample = min(home_form["matches"], away_form["matches"])
        if sample < MIN_RECENT_MATCHES:
            continue

        odds = fixture_odds(m["home"], m["away"], day)
        if not odds:
            continue

        fixtures.append({
            "home": m["home"],
            "away": m["away"],
            "league": m.get("league", "Unknown"),
            "fixture_date": day,
            "fixture_id": f'{m["home"]}||{m["away"]}||{day}',
            "home_form": home_form,
            "away_form": away_form,
            "odds": odds,
        })

    report["stages"]["fixture_and_odds"] = {
        "fixtures_with_min_form_and_current_odds": len(fixtures),
        "odds_rule": "same fixture + same local calendar date",
        "odds_source": "football-data.co.uk CSV only",
    }
    print(f"[1/4] Current-odds fixtures: {len(fixtures)}")

    if not fixtures:
        report["run_status"] = "NO_CURRENT_ODDS"
        report["decision_status"] = "NO_BET_CURRENT_ODDS_UNAVAILABLE"
        report["reason"] = "Bugünün maçları için doğrulanabilir güncel oran bulunamadı; eski oran veya scraper verisi kullanılmadı."
        return _write(report, started)

    scored = []
    for f in fixtures:
        probs = _market_probabilities(f["home_form"], f["away_form"], None)
        candidates = []
        for market, engines in probs.items():
            odds = f["odds"].get(market)
            if not odds:
                continue
            market_p = _devig_probability(f["odds"], market)
            reference_p = market_p if market_p is not None else 1.0 / odds
            stat_p = engines[0]
            edge = stat_p - reference_p
            ev = stat_p * odds - 1.0
            candidates.append((edge, ev, market))
        if candidates:
            scored.append((max(candidates), f))
    scored.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)
    shortlist = [x[1] for x in scored[:MAX_WEB_FIXTURES]]

    report["stages"]["prefilter"] = {
        "shortlist": len(shortlist),
        "max_web_fixtures": MAX_WEB_FIXTURES,
        "ranking": "stat_probability minus de-vigged market probability, then EV",
    }
    print(f"[2/4] Web-intelligence shortlist: {len(shortlist)}")

    finalists = []
    for idx, f in enumerate(shortlist, 1):
        if _remaining(started) <= 0:
            report["stages"]["deadline"] = "reached_before_web_completion"
            break
        try:
            intel = analyze_match(f["home"], f["away"], limit_per_query=5)
            probs = _market_probabilities(f["home_form"], f["away_form"], intel)
            fixture = {
                "fixture_id": f["fixture_id"],
                "home": f["home"],
                "away": f["away"],
                "fixture_date": day,
            }
            analyses = analyze_fixture_markets(
                fixture,
                probs,
                min(1.0, min(f["home_form"]["matches"], f["away_form"]["matches"]) / 8),
                odds_override=f["odds"],
            )
            good = [
                m for m in analyses
                if m.get("decision") == "ANALYZE"
                and m.get("value_edge_pct", 0) >= MIN_VALUE_EDGE * 100
            ]
            if good:
                best = max(good, key=lambda x: (x.get("ev_pct", -999), x.get("confidence_10", 0)))
                finalists.append({
                    "home": f["home"],
                    "away": f["away"],
                    "league": f["league"],
                    "market": best["market"],
                    "odds": best["odds"],
                    "model_probability_pct": best["model_probability_pct"],
                    "market_probability_pct": best["market_probability_pct"],
                    "value_edge_pct": best["value_edge_pct"],
                    "ev_pct": best["ev_pct"],
                    "confidence_10": best["confidence_10"],
                    "form_sample": min(f["home_form"]["matches"], f["away_form"]["matches"]),
                    "web_confidence": intel.get("confidence", 0.0),
                    "risk_flags": intel.get("risk_flags", []),
                    "consensus": best.get("consensus"),
                    "odds_source": "football-data.co.uk",
                })
            else:
                report["rejected"].append({
                    "home": f["home"], "away": f["away"], "reason": "final_gate"
                })
        except Exception as exc:
            report["rejected"].append({
                "home": f["home"], "away": f["away"],
                "reason": f"analysis_error:{type(exc).__name__}",
            })
        print(f"    verified {idx}/{len(shortlist)}")

    finalists.sort(
        key=lambda x: (x["ev_pct"], x["value_edge_pct"], x["confidence_10"]),
        reverse=True,
    )

    coupon = []
    seen_fixtures = set()
    seen_markets = set()
    for candidate in finalists:
        fixture_key = (candidate["home"], candidate["away"])
        market_key = candidate["market"]
        if fixture_key in seen_fixtures:
            continue
        if market_key in seen_markets and len(seen_markets) >= 2:
            continue
        coupon.append(candidate)
        seen_fixtures.add(fixture_key)
        seen_markets.add(market_key)
        if len(coupon) >= MAX_COUPON_LEGS:
            break

    report["stages"]["final_gate"] = {
        "finalists": len(finalists),
        "coupon_legs": len(coupon),
        "minimum_probability_edge_pct": MIN_VALUE_EDGE * 100,
        "minimum_ev_pct": 3.0,
    }
    report["coupon"] = coupon
    report["run_status"] = "OK" if _remaining(started) >= 0 else "DEADLINE_EXCEEDED"
    report["decision_status"] = "COUPON_CANDIDATES" if coupon else "NO_BET"
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["model_notes"] = (
        "No leg is forced. value_edge_pct = model probability minus de-vigged "
        "market probability; ev_pct = model probability × decimal odds − 1. "
        "Probabilities are estimates, not guarantees."
    )
    return _write(report, started)


def _write(report, started):
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_20min_coupon.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 20-Minute Football Coupon",
        f"- Tarih: {report.get('target_date', '')}",
        f"- Durum: {report.get('decision_status', '')}",
        f"- Süre: {report.get('elapsed_seconds', 0)} sn",
        "",
    ]
    if report.get("coupon"):
        lines += [
            "| # | Maç | Market | Oran | Model | Market | Edge | EV | Consensus |",
            "|---:|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for i, x in enumerate(report["coupon"], 1):
            lines.append(
                f"| {i} | {x['home']} - {x['away']} | {x['market']} | "
                f"{x['odds']:.2f} | %{x['model_probability_pct']} | "
                f"%{x['market_probability_pct']} | %{x['value_edge_pct']:+.2f} | "
                f"%{x['ev_pct']:+.2f} | {x.get('consensus', '')} |"
            )
    else:
        lines.append("**NO BET:** Güncel ve yeterli doğrulama sağlayan aday oluşmadı.")
    (out / "latest_20min_coupon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(f"RESULT: {report.get('decision_status')} | legs={len(report.get('coupon', []))}")
    return report


if __name__ == "__main__":
    run()
