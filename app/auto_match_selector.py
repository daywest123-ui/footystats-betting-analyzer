"""Automatic football value scanner using keyless public data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.football_data_client import load_openfootball, recent_form, fixture_odds
from app.open_web_intelligence import analyze_match
from app.signal_fusion import fuse
from app.odds_pipeline import analyze_fixture_markets

_OPEN_MATCHES = []


def _empty_form() -> dict:
    return {
        "matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0,
        "over25_rate": 0.5, "btts_rate": 0.5, "source": "none"
    }


def discover_fixtures(date: datetime) -> list[dict]:
    global _OPEN_MATCHES
    _OPEN_MATCHES = load_openfootball()
    day = date.date().isoformat()
    fixtures = []
    for m in _OPEN_MATCHES:
        if m["date"] != day or m.get("finished"):
            continue
        fixtures.append({
            "home": m["home"], "away": m["away"], "league": m["league"],
            "fixture_date": m["date"],
            "fixture_id": f"{m['home']}||{m['away']}||{m['date']}",
            "source": m.get("source", "openfootball/football.json"),
        })
    fixtures.sort(key=lambda x: (x.get("league", ""), x.get("home", "")))
    return fixtures[:100]


def _recent_form(team: str | None, before: str) -> dict:
    if not team or not _OPEN_MATCHES:
        return _empty_form()
    return recent_form(_OPEN_MATCHES, team, before, 8)


def _clamp_probability(value: float) -> float:
    return max(0.05, min(0.95, float(value)))


def _market_probabilities(
    home_form: dict, away_form: dict, intelligence: dict | None = None
) -> dict[str, tuple[float, float, float]]:
    """Return separate stat, prediction and web components."""
    h_o, a_o = home_form.get("over25_rate", .5), away_form.get("over25_rate", .5)
    h_b, a_b = home_form.get("btts_rate", .5), away_form.get("btts_rate", .5)
    h_ppg, a_ppg = home_form.get("points_per_game", 1.0), away_form.get("points_per_game", 1.0)
    h_gd, a_gd = home_form.get("goal_diff_per_game", 0.0), away_form.get("goal_diff_per_game", 0.0)

    goal_signal = (h_o + a_o) / 2
    btts_signal = (h_b + a_b) / 2
    form_edge = max(-1.0, min(1.0, (h_ppg - a_ppg) / 3.0))
    gd_edge = max(-1.0, min(1.0, (h_gd - a_gd) / 3.0))

    # Statistical component: form and goal-difference.
    home_stat = _clamp_probability(0.50 + 0.13 * form_edge + 0.09 * gd_edge + 0.03)
    btts_stat = _clamp_probability(0.35 + 0.40 * btts_signal)
    over_stat = _clamp_probability(0.35 + 0.40 * goal_signal)

    # Prediction component uses a different shrinkage transform.
    home_pred = _clamp_probability(0.50 + 0.10 * form_edge + 0.05 * gd_edge + 0.02)
    btts_pred = _clamp_probability(0.40 + 0.32 * btts_signal)
    over_pred = _clamp_probability(0.40 + 0.32 * goal_signal)

    # Web evidence is bounded and confidence-weighted; article count alone
    # cannot move a probability by more than six percentage points.
    web_score = float((intelligence or {}).get("web_score", 0.0))
    web_conf = max(0.0, min(1.0, float((intelligence or {}).get("confidence", 0.0))))
    web_shift = max(-0.06, min(0.06, web_score * 0.10 * web_conf))
    web_component = _clamp_probability(0.50 + web_shift)

    return {
        "home_win": (home_stat, home_pred, web_component),
        "btts_yes": (btts_stat, btts_pred, web_component),
        "over_2_5": (over_stat, over_pred, web_component),
    }


def _stat_probability(home_form: dict, away_form: dict) -> float:
    h_ppg, a_ppg = home_form["points_per_game"], away_form["points_per_game"]
    form_edge = max(-1.0, min(1.0, (h_ppg - a_ppg) / 3.0))
    gd_edge = max(-1.0, min(1.0,
        (home_form["goal_diff_per_game"] - away_form["goal_diff_per_game"]) / 3.0))
    totals_edge = ((home_form["over25_rate"] + away_form["over25_rate"]) / 2.0) - 0.5
    btts_edge = ((home_form["btts_rate"] + away_form["btts_rate"]) / 2.0) - 0.5
    raw = 0.50 + 0.16 * form_edge + 0.10 * gd_edge + 0.03 * totals_edge + 0.03 * btts_edge + 0.04
    n = min(home_form["matches"], away_form["matches"])
    cap = 0.50 if n < 3 else 0.55 if n < 5 else 0.62 if n < 8 else 0.68
    return max(1.0 - cap, min(cap, raw))


def score_fixture(fixture: dict) -> dict:
    day = str(fixture.get("fixture_date") or datetime.now(timezone.utc).date().isoformat())[:10]
    home_form = _recent_form(fixture.get("home"), day)
    away_form = _recent_form(fixture.get("away"), day)
    min_matches = min(home_form["matches"], away_form["matches"])
    stat_probability = _stat_probability(home_form, away_form)
    intel = analyze_match(fixture["home"], fixture["away"])
    fused = fuse(stat_probability, float(intel.get("web_score", 0.0)),
                 float(intel.get("confidence", 0.0)))
    if min_matches < 3:
        status = "INSUFFICIENT_DATA"
        fused["final_probability"] = 0.5
        fused["category"] = "AVOID"
    elif min_matches < 5:
        status = "LOW_SAMPLE"
        fused["final_probability"] = min(0.55, max(0.45, float(fused["final_probability"])))
    elif min_matches < 8:
        status = "MEDIUM_SAMPLE"
        fused["final_probability"] = min(0.62, max(0.38, float(fused["final_probability"])))
    else:
        status = "FULL_SAMPLE"
        fused["final_probability"] = min(0.68, max(0.32, float(fused["final_probability"])))
    return {
        **fixture,
        "data_quality": {"min_recent_matches": min_matches, "status": status},
        "form": {"home": home_form, "away": away_form},
        "intelligence": intel, "signal": fused
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    fixtures = discover_fixtures(now)
    results = [score_fixture(f) for f in fixtures]
    eligible = []
    odds_matches = 0

    for item in results:
        item["market_analysis"] = []
        if item["data_quality"]["min_recent_matches"] < 5:
            continue
        day = item["fixture_date"][:10]
        try:
            odds = fixture_odds(item["home"], item["away"], day)
            if odds:
                odds_matches += 1
            probs = _market_probabilities(item["form"]["home"], item["form"]["away"], item["intelligence"])
            item["market_analysis"] = analyze_fixture_markets(
                item, probs, min(1.0, item["data_quality"]["min_recent_matches"] / 8),
                odds_override=odds,
            )
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            item["odds_error"] = f"{type(exc).__name__}: {exc}"

        if any(m.get("decision") == "ANALYZE" for m in item["market_analysis"]):
            eligible.append(item)

    eligible.sort(key=lambda x: max(
        (m.get("confidence_10", 0) for m in x.get("market_analysis", [])), default=0
    ), reverse=True)
    results.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)

    insufficient = bool(results) and not any(
        r["data_quality"]["min_recent_matches"] >= 5 for r in results
    )
    run_status = "DEGRADED_DATA_SOURCE" if not results else (
        "INSUFFICIENT_OPEN_DATA" if insufficient else "OK"
    )
    decision_status = (
        "NO_BET_DATA_UNAVAILABLE" if run_status != "OK" else
        ("NO_BET" if not eligible else "BET_CANDIDATES")
    )

    report = {
        "generated_at": now.isoformat(),
        "run_status": run_status,
        "decision_status": decision_status,
        "data_sources": [
            "openfootball/football.json",
            "football-data.co.uk downloadable odds",
            "OddsHarvester current odds when available",
            "public web intelligence",
        ],
        "fixtures_scanned": len(results),
        "matches_with_odds": odds_matches,
        "eligible_matches": len(eligible),
        "model_notes": (
            "Consensus combines recent-form statistics, a separately weighted "
            "prediction component, current de-vigged market probability when "
            "available, and bounded public web intelligence. "
            "Probabilities are estimates, not guarantees."
        ),
        "top_matches": eligible[:5],
        "all_scanned": results[:50],
    }

    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\\n===== OPEN DATA FOOTBALL ANALYZER =====")
    print(f"Fixtures scanned: {len(results)} | Odds found: {odds_matches} | Eligible: {len(eligible)}")
    if eligible:
        for n, item in enumerate(eligible[:5], 1):
            best = next(m for m in item["market_analysis"] if m.get("decision") == "ANALYZE")
            print(
                f"#{n} | {item['home']} vs {item['away']} | {best['market']} | "
                f"odds={best['odds']:.2f} | model={best['model_probability_pct']}% | "
                f"edge={best['value_edge_pct']:+.2f}% | EV={best['ev_pct']:+.2f}% | "
                f"confidence={best['confidence_10']}/10"
            )
    elif run_status != "OK":
        print(f"NO BET: {run_status}")
    else:
        print("NO BET: kriterleri geçen market bulunamadı.")


if __name__ == "__main__":
    main()
