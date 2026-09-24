"""Automatic football value scanner using keyless public data."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.football_data_client import load_openfootball, recent_form, fixture_odds
from app.odds_harvester_client import current_fixtures as current_odds_fixtures
from app.open_web_intelligence import analyze_match
from app.odds_pipeline import analyze_fixture_markets

LOCAL_TZ = ZoneInfo("Europe/Istanbul")
_OPEN_MATCHES = []


def _empty_form() -> dict:
    return {
        "matches": 0, "points_per_game": 0.5, "goal_diff_per_game": 0.0,
        "goals_for_per_game": 1.25, "goals_against_per_game": 1.25,
        "over25_rate": 0.5, "btts_rate": 0.5, "source": "none"
    }


def discover_fixtures(date: datetime) -> list[dict]:
    global _OPEN_MATCHES
    _OPEN_MATCHES = load_openfootball()
    day = date.astimezone(LOCAL_TZ).date().isoformat()
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
    if fixtures:
        return fixtures[:100]

    # If openfootball has no same-day schedule, use the current odds feed as
    # a fixture-discovery fallback. This prevents a silent zero-fixture scan.
    try:
        fallback = current_odds_fixtures(day)
    except Exception:
        fallback = []
    return fallback[:100]


def _recent_form(team: str | None, before: str) -> dict:
    if not team or not _OPEN_MATCHES:
        return _empty_form()
    return recent_form(_OPEN_MATCHES, team, before, 8)


def _clamp_probability(value: float) -> float:
    return max(0.05, min(0.95, float(value)))


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_home_probability(home_form: dict, away_form: dict) -> float:
    """Bounded expected-goals model; no future information is used."""
    h_attack = float(home_form.get("goals_for_per_game", 1.25))
    h_defense = float(home_form.get("goals_against_per_game", 1.25))
    a_attack = float(away_form.get("goals_for_per_game", 1.25))
    a_defense = float(away_form.get("goals_against_per_game", 1.25))

    # Shrink sparse samples toward league-average scoring.
    h_n = min(8, int(home_form.get("matches", 0)))
    a_n = min(8, int(away_form.get("matches", 0)))
    h_w = h_n / 8.0
    a_w = a_n / 8.0
    h_attack = 1.25 * (1 - h_w) + h_attack * h_w
    h_defense = 1.25 * (1 - h_w) + h_defense * h_w
    a_attack = 1.25 * (1 - a_w) + a_attack * a_w
    a_defense = 1.25 * (1 - a_w) + a_defense * a_w

    # Home advantage is intentionally modest.
    home_lambda = max(0.35, min(3.20, 0.55 * h_attack + 0.45 * a_defense + 0.10))
    away_lambda = max(0.30, min(2.80, 0.55 * a_attack + 0.45 * h_defense - 0.05))

    home_win = 0.0
    for hg in range(0, 8):
        ph = _poisson_pmf(hg, home_lambda)
        for ag in range(0, 8):
            if hg > ag:
                home_win += ph * _poisson_pmf(ag, away_lambda)
    return _clamp_probability(home_win)


def _market_probabilities(
    home_form: dict, away_form: dict, intelligence: dict | None = None
) -> dict[str, tuple[float, float, float]]:
    h_o, a_o = home_form.get("over25_rate", .5), away_form.get("over25_rate", .5)
    h_b, a_b = home_form.get("btts_rate", .5), away_form.get("btts_rate", .5)
    h_ppg, a_ppg = home_form.get("points_per_game", 1.0), away_form.get("points_per_game", 1.0)
    h_gd, a_gd = home_form.get("goal_diff_per_game", 0.0), away_form.get("goal_diff_per_game", 0.0)

    goal_signal = (h_o + a_o) / 2
    btts_signal = (h_b + a_b) / 2
    form_edge = max(-1.0, min(1.0, (h_ppg - a_ppg) / 3.0))
    gd_edge = max(-1.0, min(1.0, (h_gd - a_gd) / 3.0))

    poisson_home = _poisson_home_probability(home_form, away_form)
    form_home = _clamp_probability(0.50 + 0.13 * form_edge + 0.09 * gd_edge + 0.03)

    # Independent model components; web evidence is a small bounded adjustment
    # and cannot manufacture a large probability from article volume alone.
    home_stat = _clamp_probability(0.65 * poisson_home + 0.35 * form_home)
    home_pred = _clamp_probability(0.75 * poisson_home + 0.25 * form_home)
    btts_stat = _clamp_probability(0.35 + 0.40 * btts_signal)
    btts_pred = _clamp_probability(0.40 + 0.32 * btts_signal)
    over_stat = _clamp_probability(0.35 + 0.40 * goal_signal)
    over_pred = _clamp_probability(0.40 + 0.32 * goal_signal)

    web_score = float((intelligence or {}).get("web_score", 0.0))
    web_conf = max(0.0, min(1.0, float((intelligence or {}).get("confidence", 0.0))))
    web_shift = max(-0.06, min(0.06, web_score * 0.10 * web_conf))
    web_component = _clamp_probability(0.50 + web_shift)

    return {
        "home_win": (home_stat, home_pred, web_component),
        "btts_yes": (btts_stat, btts_pred, web_component),
        "over_2_5": (over_stat, over_pred, web_component),
    }


def score_fixture(fixture: dict) -> dict:
    day = str(fixture.get("fixture_date") or datetime.now(LOCAL_TZ).date().isoformat())[:10]
    home_form = _recent_form(fixture.get("home"), day)
    away_form = _recent_form(fixture.get("away"), day)
    min_matches = min(home_form["matches"], away_form["matches"])

    intel = analyze_match(fixture["home"], fixture["away"])
    web_score = float(intel.get("web_score", 0.0))
    web_conf = float(intel.get("confidence", 0.0))
    poisson_probability = _poisson_home_probability(home_form, away_form)
    form_edge = max(-1.0, min(1.0, (
        home_form["points_per_game"] - away_form["points_per_game"]
    ) / 3.0))
    form_probability = _clamp_probability(0.50 + 0.13 * form_edge + 0.03)
    fused_probability = _clamp_probability(
        (0.70 * poisson_probability + 0.30 * form_probability)
        * (1 - 0.08 * max(0.0, min(1.0, web_conf)))
        + (0.50 + max(-0.04, min(0.04, web_score * 0.08 * web_conf)))
        * (0.08 * max(0.0, min(1.0, web_conf)))
    )

    if min_matches < 3:
        status = "INSUFFICIENT_DATA"
        fused_probability = 0.5
    elif min_matches < 5:
        status = "LOW_SAMPLE"
        fused_probability = min(0.55, max(0.45, fused_probability))
    elif min_matches < 8:
        status = "MEDIUM_SAMPLE"
        fused_probability = min(0.62, max(0.38, fused_probability))
    else:
        status = "FULL_SAMPLE"
        fused_probability = min(0.68, max(0.32, fused_probability))

    return {
        **fixture,
        "data_quality": {"min_recent_matches": min_matches, "status": status},
        "form": {"home": home_form, "away": away_form},
        "intelligence": intel,
        "signal": {
            "stat_probability": round(poisson_probability, 4),
            "web_score": round(web_score, 4),
            "web_confidence": round(web_conf, 4),
            "final_probability": round(fused_probability, 4),
            "category": "VALUE" if fused_probability >= 0.58 else "WATCH",
        },
    }


def main() -> None:
    now = datetime.now(LOCAL_TZ)
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
            probs = _market_probabilities(
                item["form"]["home"], item["form"]["away"], item["intelligence"]
            )
            item["market_analysis"] = analyze_fixture_markets(
                item, probs,
                min(1.0, item["data_quality"]["min_recent_matches"] / 8),
                odds_override=odds,
            )
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            item["odds_error"] = f"{type(exc).__name__}: {exc}"

        if any(m.get("decision") == "ANALYZE" for m in item["market_analysis"]):
            eligible.append(item)

    eligible.sort(
        key=lambda x: max(
            (m.get("ev_pct", -999) for m in x.get("market_analysis", [])),
            default=-999,
        ),
        reverse=True,
    )
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
            "Home-win probability now uses a bounded expected-goals/Poisson "
            "component plus recent-form component. Market odds are used only "
            "for de-vig value comparison, not as a model vote. Web intelligence "
            "is bounded to a small adjustment. Probabilities are estimates, "
            "not guarantees."
        ),
        "top_matches": eligible[:5],
        "all_scanned": results[:50],
    }

    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n===== OPEN DATA FOOTBALL ANALYZER =====")
    print(f"Fixtures scanned: {len(results)} | Odds found: {odds_matches} | Eligible: {len(eligible)}")
    for n, item in enumerate(eligible[:5], 1):
        best = next(m for m in item["market_analysis"] if m.get("decision") == "ANALYZE")
        print(
            f"#{n} | {item['home']} vs {item['away']} | {best['market']} | "
            f"odds={best['odds']:.2f} | model={best['model_probability_pct']}% | "
            f"edge={best['value_edge_pct']:+.2f}% | EV={best['ev_pct']:+.2f}% | "
            f"confidence={best['confidence_10']}/10"
        )
    if not eligible:
        print("NO BET: kriterleri geçen market bulunamadı.")


if __name__ == "__main__":
    main()
