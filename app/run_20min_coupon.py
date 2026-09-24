"""20-minute football coupon pipeline.

Analysis/paper-selection only. It never places bets.
Uses only same-date retrieved odds; if current odds are unavailable,
it returns NO BET instead of fabricating or reusing stale prices.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.football_data_client import load_openfootball, recent_form, fixture_odds
from app.open_web_intelligence import analyze_match
from app.odds_pipeline import analyze_fixture_markets
from app.auto_match_selector import _market_probabilities

MAX_WEB_FIXTURES = 12
MAX_COUPON_LEGS = 4
MIN_RECENT_MATCHES = 5
MIN_VALUE_EDGE = 0.025
MAX_RUNTIME_SECONDS = 20 * 60

def run():
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    report = {
        "generated_at": now.isoformat(), "target_date": day,
        "pipeline": "20MIN_V1", "run_status": "STARTED",
        "decision_status": "NO_BET", "stages": {}, "coupon": [], "rejected": []
    }
    print("=== 20-MIN FOOTBALL COUPON ENGINE ===")
    print(f"Target date: {day}")

    matches = load_openfootball()
    # If the free fixture feeds do not expose today's matches, use the same
    # current OddsHarvester scrape that supplies live odds.
    if not any(m.get("date") == day and not m.get("finished") for m in matches):
        try:
            from app.odds_harvester_client import current_fixtures
            fallback_fixtures = current_fixtures(day)
            if fallback_fixtures:
                matches.extend(fallback_fixtures)
                print(f"OddsHarvester current fixtures: {len(fallback_fixtures)}")
        except Exception as exc:
            print(f"OddsHarvester fixture fallback unavailable: {type(exc).__name__}")
    fixtures = []
    for m in matches:
        if m.get("date") != day or m.get("finished"):
            continue
        h = recent_form(matches, m["home"], day, 8)
        a = recent_form(matches, m["away"], day, 8)
        if min(h["matches"], a["matches"]) < MIN_RECENT_MATCHES:
            continue
        odds = fixture_odds(m["home"], m["away"], day)
        if not odds:
            continue
        fixtures.append({
            "home": m["home"], "away": m["away"], "league": m["league"],
            "fixture_date": day, "home_form": h, "away_form": a, "odds": odds
        })
    report["stages"]["fixture_and_odds"] = {
        "fixtures_with_min_form_and_current_odds": len(fixtures),
        "odds_rule": "same fixture + same calendar date only"
    }
    print(f"[1/4] Current-odds fixtures: {len(fixtures)}")
    if not fixtures:
        report["run_status"] = "NO_CURRENT_ODDS"
        report["decision_status"] = "NO_BET_CURRENT_ODDS_UNAVAILABLE"
        report["reason"] = "Bugünün maçları için doğrulanabilir güncel oran bulunamadı; eski oran kullanılmadı."
        return _write(report)

    scored = []
    for f in fixtures:
        probs = _market_probabilities(f["home_form"], f["away_form"], None)
        quick = []
        for market, engines in probs.items():
            odds = f["odds"].get(market)
            if odds:
                p = sum(engines) / len(engines)
                quick.append((p - 1.0 / odds, market))
        if quick:
            best_edge, best_market = max(quick)
            scored.append((best_edge, best_market, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    shortlist = [x[2] for x in scored[:MAX_WEB_FIXTURES]]
    report["stages"]["prefilter"] = {
        "shortlist": len(shortlist), "max_web_fixtures": MAX_WEB_FIXTURES
    }
    print(f"[2/4] Web-intelligence shortlist: {len(shortlist)}")

    finalists = []
    for idx, f in enumerate(shortlist, 1):
        if time.monotonic() - started >= MAX_RUNTIME_SECONDS:
            report["stages"]["deadline"] = "reached_before_completion"
            break
        try:
            intel = analyze_match(f["home"], f["away"])
            probs = _market_probabilities(f["home_form"], f["away_form"], intel)
            fixture = {
                "fixture_id": f'{f["home"]}||{f["away"]}||{day}',
                "home": f["home"], "away": f["away"], "fixture_date": day
            }
            analyses = analyze_fixture_markets(
                fixture, probs,
                min(1.0, min(f["home_form"]["matches"], f["away_form"]["matches"]) / 8)
            )
            good = [
                m for m in analyses
                if m.get("decision") == "ANALYZE"
                and m.get("value_edge_pct", 0) >= MIN_VALUE_EDGE * 100
            ]
            if good:
                best = max(good, key=lambda x: (x.get("confidence_10", 0), x.get("value_edge_pct", 0)))
                finalists.append({
                    "home": f["home"], "away": f["away"], "league": f["league"],
                    "market": best["market"], "odds": best["odds"],
                    "model_probability_pct": best["model_probability_pct"],
                    "value_edge_pct": best["value_edge_pct"],
                    "confidence_10": best["confidence_10"],
                    "form_sample": min(f["home_form"]["matches"], f["away_form"]["matches"]),
                    "web_confidence": intel.get("confidence", 0.0),
                    "risk_flags": intel.get("risk_flags", [])
                })
            else:
                report["rejected"].append({"home": f["home"], "away": f["away"], "reason": "final_gate"})
        except Exception as exc:
            report["rejected"].append({
                "home": f["home"], "away": f["away"],
                "reason": f"analysis_error:{type(exc).__name__}"
            })
        print(f"    verified {idx}/{len(shortlist)}")

    finalists.sort(key=lambda x: (x["confidence_10"], x["value_edge_pct"]), reverse=True)
    coupon = []
    seen = set()
    for x in finalists:
        key = (x["home"], x["away"])
        if key in seen or x["confidence_10"] < 6.0 or x["value_edge_pct"] < 2.5:
            continue
        coupon.append(x); seen.add(key)
        if len(coupon) >= MAX_COUPON_LEGS:
            break

    report["stages"]["final_gate"] = {
        "finalists": len(finalists), "coupon_legs": len(coupon),
        "minimum_confidence": 6.0, "minimum_value_edge_pct": 2.5
    }
    report["coupon"] = coupon
    report["run_status"] = "OK"
    report["decision_status"] = "COUPON_CANDIDATES" if coupon else "NO_BET"
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["model_notes"] = "Probabilities are estimates, not guarantees. No leg is forced; only same-date odds are eligible."
    return _write(report)

def _write(report):
    report["elapsed_seconds"] = round(report.get("elapsed_seconds", 0.0), 2)
    out = Path("reports"); out.mkdir(exist_ok=True)
    (out / "latest_20min_coupon.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 20-Minute Football Coupon",
        f"- Tarih: {report.get('target_date', '')}",
        f"- Durum: {report.get('decision_status', '')}",
        f"- Süre: {report.get('elapsed_seconds', 0)} sn", ""
    ]
    if report.get("coupon"):
        lines += [
            "| # | Maç | Market | Oran | Model | Value | Güven |",
            "|---:|---|---|---:|---:|---:|---:|"
        ]
        for i, x in enumerate(report["coupon"], 1):
            lines.append(
                f"| {i} | {x['home']} - {x['away']} | {x['market']} | "
                f"{x['odds']:.2f} | %{x['model_probability_pct']} | "
                f"%{x['value_edge_pct']:+.2f} | {x['confidence_10']}/10 |"
            )
    else:
        lines.append("**NO BET:** Güncel ve yeterli doğrulama sağlayan aday oluşmadı.")
    (out / "latest_20min_coupon.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"RESULT: {report.get('decision_status')} | legs={len(report.get('coupon', []))}")
    return report

if __name__ == "__main__":
    run()
