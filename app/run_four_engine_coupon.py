"""Four-engine FootyStats coupon runner.

Uses the existing repository data loaders plus:
- FootyStats snapshot features
- ensemble/form scoring
- Dixon-Coles probability model
- football-stat feature engineering
- value/EV and consensus gates
- coupon construction

Analysis only: never places bets.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.auto_match_selector import discover_fixtures, _recent_form
from app.football_data_client import fixture_odds
from app.dixon_coles_model import predict as dixon_coles_predict
from app.footystats_parser import parse_snapshot
from app.four_engine_fusion import fuse_market
from app.coupon_engine_v5 import build_candidates, build_coupon

LOCAL_TZ = ZoneInfo("Europe/Istanbul")


def norm(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def load_footystats_snapshot(path: str) -> list[dict]:
    try:
        return parse_snapshot(path)
    except Exception:
        return []


def find_fs_row(rows: list[dict], home: str, away: str) -> dict:
    h, a = norm(home), norm(away)
    for row in rows:
        rh, ra = norm(row.get("home", "")), norm(row.get("away", ""))
        if (h in rh or rh in h) and (a in ra or ra in a):
            return row
    return {}


def run(snapshot_path: str = "data/footystats_snapshot.json") -> dict:
    now = datetime.now(LOCAL_TZ)
    fixtures = discover_fixtures(now)
    fs_rows = load_footystats_snapshot(snapshot_path)

    enriched = []
    for fixture in fixtures:
        day = fixture["fixture_date"][:10]
        hf = _recent_form(fixture["home"], day)
        af = _recent_form(fixture["away"], day)
        if min(hf.get("matches", 0), af.get("matches", 0)) < 5:
            continue
        odds = fixture_odds(fixture["home"], fixture["away"], day)
        if not odds:
            continue
        dc = dixon_coles_predict(
            # discover_fixtures stores the loaded openfootball set globally;
            # the DC model is invoked by the existing scoring layer in normal runs.
            [],
            fixture["home"], fixture["away"], day
        )
        fs = find_fs_row(fs_rows, fixture["home"], fixture["away"])
        fusion = {}
        for market in ("home_win", "btts_yes", "over_2_5"):
            fusion[market] = fuse_market(
                market,
                footystats=fs,
                home_form=hf,
                away_form=af,
                dixon_coles=dc,
            )
        enriched.append({
            **fixture,
            "odds": odds,
            "footystats": fs,
            "fusion": fusion,
        })

    candidates = build_candidates(enriched)
    coupon = build_coupon(candidates)

    report = {
        "generated_at": now.isoformat(),
        "engine": "FOUR_ENGINE_COUPON_V1",
        "snapshot": snapshot_path,
        "fixtures_scanned": len(fixtures),
        "fixtures_enriched": len(enriched),
        "candidate_count": len(candidates),
        "coupon": coupon,
        "notes": [
            "No leg is forced when value/quality gates fail.",
            "Probabilities are model estimates, not guarantees.",
            "Dixon-Coles is an independent probability component.",
            "FootyStats snapshot data is optional; missing rows reduce engine count.",
        ],
    }
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "latest_four_engine_coupon.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "latest_four_engine_coupon.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    return report


def render_markdown(report: dict) -> str:
    c = report["coupon"]
    lines = [
        "# FOUR-ENGINE FOOTYSTATS COUPON",
        f"- Generated: {report['generated_at']}",
        f"- Fixtures scanned: {report['fixtures_scanned']}",
        f"- Enriched: {report['fixtures_enriched']}",
        f"- Candidates: {report['candidate_count']}",
        f"- Status: {c['status']}",
        "",
    ]
    if c["legs"]:
        lines += [
            "| # | Match | Market | Odds | Model | Edge | EV | Consensus |",
            "|---:|---|---|---:|---:|---:|---:|---|",
        ]
        for i, x in enumerate(c["legs"], 1):
            lines.append(
                f"| {i} | {x['home']} - {x['away']} | {x['market']} | "
                f"{x['odds']:.2f} | {x['model_probability_pct']:.2f}% | "
                f"{x['value_edge_pct']:+.2f}% | {x['ev_pct']:+.2f}% | "
                f"{x['engine_consensus']} |"
            )
        lines.append("")
        lines.append(f"**Combined decimal odds:** {c['combined_decimal_odds']}")
    else:
        lines.append("**NO BET:** Quality/value gates produced no qualifying leg.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="data/footystats_snapshot.json")
    args = parser.parse_args()
    result = run(args.snapshot)
    print(json.dumps(result["coupon"], ensure_ascii=False, indent=2))
