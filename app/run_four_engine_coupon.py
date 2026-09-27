"""Four-engine FootyStats coupon runner. Analysis only; never places bets."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import app.auto_match_selector as selector
from app.football_data_client import fixture_odds
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
    fixtures = selector.discover_fixtures(now)
    fs_rows = load_footystats_snapshot(snapshot_path)
    matches = selector._OPEN_MATCHES
    enriched = []

    for fixture in fixtures:
        day = fixture["fixture_date"][:10]
        hf = selector._recent_form(fixture["home"], day)
        af = selector._recent_form(fixture["away"], day)
        if min(hf.get("matches", 0), af.get("matches", 0)) < 5:
            continue
        odds = fixture_odds(fixture["home"], fixture["away"], day)
        if not odds:
            continue
        from app.dixon_coles_model import predict as dixon_coles_predict
        dc = dixon_coles_predict(matches, fixture["home"], fixture["away"], day)
        fs = find_fs_row(fs_rows, fixture["home"], fixture["away"])
        fusion = {
            market: fuse_market(
                market, footystats=fs, home_form=hf, away_form=af,
                dixon_coles=dc
            )
            for market in ("home_win", "btts_yes", "over_2_5")
        }
        enriched.append({
            **fixture, "odds": odds, "footystats": fs, "fusion": fusion
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
            "Dixon-Coles uses the same historical match set as the existing analyzer.",
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
        f"- Status: {c['status']}", "",
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
        lines += ["", f"**Combined decimal odds:** {c['combined_decimal_odds']}"]
    else:
        lines.append("**NO BET:** Quality/value gates produced no qualifying leg.")
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="data/footystats_snapshot.json")
    args = parser.parse_args()
    print(json.dumps(run(args.snapshot)["coupon"], ensure_ascii=False, indent=2))
