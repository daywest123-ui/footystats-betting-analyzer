"""Automatic football value scanner using keyless public data."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.football_data_client import load_openfootball, recent_form, fixture_odds
from app.open_web_intelligence import analyze_match
from app.odds_pipeline import analyze_fixture_markets
from app.dixon_coles_model import predict as dixon_coles_predict
from app.market_probabilities import add_htft_probabilities, as_model_market_rows, build_market_probabilities
from app.nesine_odds_client import _payload as load_nesine_payload

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
    now = date.astimezone(LOCAL_TZ)
    base_day = now.date()
    target = base_day.isoformat()

    fixtures = [
        {
            "home": m["home"], "away": m["away"], "league": m["league"],
            "fixture_date": m["date"],
            "fixture_id": f"{m['home']}||{m['away']}||{m['date']}",
            "source": m.get("source", "openfootball/football.json"),
        }
        for m in _OPEN_MATCHES
        if m["date"] == target and not m.get("finished")
    ]
    if fixtures:
        fixtures.sort(key=lambda x: (x.get("league", ""), x.get("home", "")))
        print(f"[FixtureDiscovery] Using {len(fixtures)} open-data fixtures for {target}")
        return fixtures[:100]

    # Fallback to the live public Nesine bulletin when OpenFootball has no
    # fixture for the local calendar day. Only football (TYPE/GT == 1) and
    # upcoming kickoff times are accepted.
    nesine_day = now.strftime("%d.%m.%Y")
    try:
        payload = load_nesine_payload()
        events = (payload.get("sg") or {}).get("EA") or []
    except Exception as exc:
        print(f"[FixtureDiscovery] Nesine fallback unavailable: {type(exc).__name__}: {exc}")
        return []

    fallback = []
    for event in events:
        if str(event.get("D") or "") != nesine_day:
            continue
        if str(event.get("TYPE") or "") != "1" or str(event.get("GT") or "") != "1":
            continue
        home = str(event.get("HN") or "").strip()
        away = str(event.get("AN") or "").strip()
        if not home or not away:
            continue
        try:
            kickoff = datetime.fromtimestamp(int(event.get("ESD")) / 1000, LOCAL_TZ)
        except (TypeError, ValueError, OSError):
            continue
        if kickoff.date() != base_day or kickoff <= now:
            continue
        fallback.append({
            "home": home,
            "away": away,
            "league": "Nesine public bulletin",
            "fixture_date": target,
            "fixture_id": f"{home}||{away}||{target}",
            "source": "nesine.com public bulletin",
            "kickoff": event.get("T"),
        })

    fallback.sort(key=lambda x: (x.get("kickoff", ""), x.get("home", "")))
    print(f"[FixtureDiscovery] OpenFootball had no {target} fixtures; using {len(fallback)} upcoming Nesine football fixtures")
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
    h_attack = float(home_form.get("goals_for_per_game", 1.25))
    h_defense = float(home_form.get("goals_against_per_game", 1.25))
    a_attack = float(away_form.get("goals_for_per_game", 1.25))
    a_defense = float(away_form.get("goals_against_per_game", 1.25))
    h_w = min(8, int(home_form.get("matches", 0))) / 8.0
    a_w = min(8, int(away_form.get("matches", 0))) / 8.0
    h_attack = 1.25 * (1 - h_w) + h_attack * h_w
    h_defense = 1.25 * (1 - h_w) + h_defense * h_w
    a_attack = 1.25 * (1 - a_w) + a_attack * a_w
    a_defense = 1.25 * (1 - a_w) + a_defense * a_w
    home_lambda = max(0.35, min(3.20, 0.55 * h_attack + 0.45 * a_defense + 0.10))
    away_lambda = max(0.30, min(2.80, 0.55 * a_attack + 0.45 * h_defense - 0.05))
    home_win = 0.0
    for hg in range(8):
        ph = _poisson_pmf(hg, home_lambda)
        for ag in range(8):
            if hg > ag:
                home_win += ph * _poisson_pmf(ag, away_lambda)
    return _clamp_probability(home_win)


def score_fixture(fixture: dict) -> dict:
    day = str(fixture.get("fixture_date") or datetime.now(LOCAL_TZ).date().isoformat())[:10]
    home_form = _recent_form(fixture.get("home"), day)
    away_form = _recent_form(fixture.get("away"), day)
    min_matches = min(home_form["matches"], away_form["matches"])
    intel = analyze_match(fixture["home"], fixture["away"])
    dc = dixon_coles_predict(_OPEN_MATCHES, fixture["home"], fixture["away"], day)
    poisson_probability = _poisson_home_probability(home_form, away_form)
    form_edge = max(-1.0, min(1.0, (home_form["points_per_game"] - away_form["points_per_game"]) / 3.0))
    form_probability = _clamp_probability(0.50 + 0.13 * form_edge + 0.03)
    fused_probability = _clamp_probability(
        0.45 * poisson_probability + 0.45 * dc["home_win"] + 0.10 * form_probability
    )
    market_probabilities = build_market_probabilities(home_form, away_form, dc)
    market_probabilities = add_htft_probabilities(market_probabilities, intel.get("opportunities", []))
    if min_matches < 3:
        status, fused_probability = "INSUFFICIENT_DATA", 0.5
    elif min_matches < 5:
        status, fused_probability = "LOW_SAMPLE", min(0.55, max(0.45, fused_probability))
    elif min_matches < 8:
        status, fused_probability = "MEDIUM_SAMPLE", min(0.62, max(0.38, fused_probability))
    else:
        status, fused_probability = "FULL_SAMPLE", min(0.68, max(0.32, fused_probability))
    return {
        **fixture,
        "data_quality": {"min_recent_matches": min_matches, "status": status},
        "form": {"home": home_form, "away": away_form},
        "intelligence": intel,
        "dixon_coles": {k: v for k, v in dc.items() if k != "score_matrix"},
        "signal": {
            "stat_probability": round(poisson_probability, 4),
            "dixon_coles_probability": round(dc["home_win"], 4),
            "final_probability": round(fused_probability, 4),
            "category": "VALUE" if fused_probability >= 0.58 else "WATCH",
        },
        "model_markets": as_model_market_rows(market_probabilities),
        "market_probability_engines": market_probabilities,
        "htft_matrix": intel.get("opportunities", [])[:9],
    }


def main() -> None:
    now = datetime.now(LOCAL_TZ)
    fixtures = discover_fixtures(now)
    results = [score_fixture(f) for f in fixtures]
    eligible, odds_matches = [], 0

    for item in results:
        item["market_analysis"] = []
        if item["data_quality"]["min_recent_matches"] < 5:
            continue
        day = item["fixture_date"][:10]
        try:
            odds = fixture_odds(item["home"], item["away"], day)
            if odds:
                odds_matches += 1
            probs = item.get("market_probability_engines") or {}
            item["market_analysis"] = analyze_fixture_markets(
                item, probs, min(1.0, item["data_quality"]["min_recent_matches"] / 8),
                odds_override=odds,
            )
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            item["odds_error"] = f"{type(exc).__name__}: {exc}"
        if any(m.get("decision") == "ANALYZE" for m in item["market_analysis"]):
            eligible.append(item)

    eligible.sort(key=lambda x: max((m.get("ev_pct", -999) for m in x.get("market_analysis", [])), default=-999), reverse=True)
    results.sort(key=lambda x: x["signal"]["final_probability"], reverse=True)
    insufficient = bool(results) and not any(r["data_quality"]["min_recent_matches"] >= 5 for r in results)
    run_status = "DEGRADED_DATA_SOURCE" if not results else ("INSUFFICIENT_OPEN_DATA" if insufficient else "OK")
    decision_status = "NO_BET_DATA_UNAVAILABLE" if run_status != "OK" else ("NO_BET" if not eligible else "BET_CANDIDATES")

    report = {
        "generated_at": now.isoformat(), "run_status": run_status,
        "decision_status": decision_status,
        "data_sources": ["openfootball/football.json", "football-data.co.uk downloadable odds", "public web intelligence"],
        "models": ["existing Poisson/form", "Elo + Dixon-Coles", "bounded web intelligence"],
        "fixtures_scanned": len(results), "matches_with_odds": odds_matches,
        "eligible_matches": len(eligible),
        "model_notes": "Dixon-Coles adds Elo strength, time-decayed form and low-score correction. Full market layer covers MS 1/X/2, İY 1/X/2, KG VAR/YOK, ÜST/ALT 2.5, KG VAR+ÜST 2.5, Korner ÜST/ALT 8.5 and Kart ÜST/ALT 4.5. Probabilities are estimates, fair odds are 1/p, and value decisions require concrete bookmaker odds.",
        "top_matches": eligible[:5], "all_scanned": results[:50],
    }
    out = Path("reports"); out.mkdir(exist_ok=True)
    (out / "latest_auto_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== OPEN DATA FOOTBALL ANALYZER =====")
    print(f"Fixtures scanned: {len(results)} | Odds found: {odds_matches} | Eligible: {len(eligible)}")
    for n, item in enumerate(eligible[:5], 1):
        best = next(m for m in item["market_analysis"] if m.get("decision") == "ANALYZE")
        print(f"#{n} | {item['home']} vs {item['away']} | {best['market']} | odds={best['odds']:.2f} | model={best['model_probability_pct']}% | edge={best['value_edge_pct']:+.2f}% | EV={best['ev_pct']:+.2f}% | confidence={best['confidence_10']}/10")
    if results:
        print(f"Full market layer: {sum(len(x.get('model_markets', [])) for x in results)} market-model rows generated.")
    if not eligible:
        print("NO BET: kriterleri geçen fiyatlı market bulunamadı. Fiyat yoksa model fair oranı tek başına kupon üretmez.")


if __name__ == "__main__":
    main()
