"""Four-engine FootyStats coupon runner. Analysis only; never places bets."""
from __future__ import annotations
import argparse,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import app.auto_match_selector as selector
from app.football_data_client import fixture_odds
from app.footystats_parser import parse_snapshot
from app.four_engine_fusion import fuse_market
from app.coupon_engine_v5 import build_candidates,build_coupon,MARKETS
from app.open_source_intel import analyze_match as analyze_open_source_match
from app.external_prediction_sources import analyze_match as analyze_external_sources

LOCAL_TZ=ZoneInfo("Europe/Istanbul")

def norm(s):
    import re
    return re.sub(r"[^a-z0-9]+","",str(s).lower())

def load_footystats_snapshot(path):
    try:return parse_snapshot(path)
    except Exception:return []

def find_fs_row(rows,home,away):
    h,a=norm(home),norm(away)
    for row in rows:
        rh,ra=norm(row.get("home","")),norm(row.get("away",""))
        if (h in rh or rh in h) and (a in ra or ra in a):return row
    return {}

def merge_odds(base,fs):
    odds=dict(base or {})
    for key,val in (fs.get("odds") or {}).items():
        if val is not None and float(val)>1: odds[key]=float(val)
    return odds

def run(snapshot_path="data/footystats_snapshot.json"):
    now=datetime.now(LOCAL_TZ); fixtures=selector.discover_fixtures(now)
    fs_rows=load_footystats_snapshot(snapshot_path); matches=selector._OPEN_MATCHES
    enriched=[]
    from app.dixon_coles_model import predict as dixon_coles_predict
    for fixture in fixtures:
        day=fixture["fixture_date"][:10]
        hf=selector._recent_form(fixture["home"],day); af=selector._recent_form(fixture["away"],day)
        if min(hf.get("matches",0),af.get("matches",0))<5: continue
        fs=find_fs_row(fs_rows,fixture["home"],fixture["away"])
        odds=merge_odds(fixture_odds(fixture["home"],fixture["away"],day),fs)
        if not odds: continue
        dc=dixon_coles_predict(matches,fixture["home"],fixture["away"],day)
        fusion={m:fuse_market(m,footystats=fs,home_form=hf,away_form=af,dixon_coles=dc)
                for m in MARKETS if m in odds}
        enriched.append({**fixture,"odds":odds,"footystats":fs,"fusion":fusion})
    # Free external prediction layer. Evidence-only: explicit source picks are
    # recorded for cross-checking and learning; no probabilities are fabricated.
    for item in enriched:
        try:
            item["external_prediction_sources"] = analyze_external_sources(
                item["home"], item["away"]
            )
        except Exception as exc:
            item["external_prediction_sources"] = {
                "status": "ERROR", "sources": [], "consensus": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
    candidates=build_candidates(enriched); coupon=build_coupon(candidates)
    # Separate high-odds opportunity layer: HT/FT and first/second-half patterns.
    # It never forces a coupon leg and never invents bookmaker prices.
    for item in enriched:
        try:
            item["open_source_intel"] = analyze_open_source_match(item["home"], item["away"])
        except Exception as exc:
            item["open_source_intel"] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}", "opportunities": []}
    special = []
    for item in enriched:
        for opp in item.get("open_source_intel", {}).get("opportunities", []):
            special.append({
                "home": item["home"], "away": item["away"],
                "fixture_date": item["fixture_date"], **opp
            })
    special.sort(key=lambda x: x.get("model_probability", 0), reverse=True)
    report={"generated_at":now.isoformat(),"engine":"FOUR_ENGINE_COUPON_V2",
            "snapshot":snapshot_path,"fixtures_scanned":len(fixtures),
            "fixtures_enriched":len(enriched),"candidate_count":len(candidates),
            "candidate_markets":sorted({x["market"] for x in candidates}),
            "coupon":coupon,
            "open_source_special_opportunities": special[:20],
            "external_prediction_sources": {
                f"{item['home']} - {item['away']}": item.get("external_prediction_sources", {})
                for item in enriched
            },
            "notes":["FootyStats prices supplement concrete football-data prices.",
                     "No probability is fabricated when required data is unavailable.",
                     "One selection per fixture with market-family diversification.",
                     "No leg is forced when value, quality or consensus gates fail.",
                     "DataFC/Sofascore supplies a separate historical HT/FT opportunity layer; H2H is secondary evidence.",
                     "StatsBet, PitchDeep, xGaura, Predictions Footy and Kings Odds are queried as external evidence sources; only explicit match-level tips are recorded.",
                     "External source failures are neutral and never count as negative evidence or force a selection.",
                     "Probabilities are estimates, not guarantees."]}
    out=Path("reports");out.mkdir(exist_ok=True)
    (out/"latest_four_engine_coupon.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"latest_four_engine_coupon.md").write_text(render_markdown(report),encoding="utf-8")
    return report

def render_markdown(report):
    c=report["coupon"]
    lines=["# FOUR-ENGINE FOOTYSTATS COUPON V2",f"- Generated: {report['generated_at']}",
           f"- Fixtures scanned: {report['fixtures_scanned']}",f"- Enriched: {report['fixtures_enriched']}",
           f"- Candidates: {report['candidate_count']}",f"- Markets found: {', '.join(report['candidate_markets']) or 'none'}",
           f"- Status: {c['status']}",""]
    if c["legs"]:
        lines+=["| # | Match | Market | Odds | Model | Edge | EV | Consensus |",
                 "|---:|---|---|---:|---:|---:|---:|---|"]
        for i,x in enumerate(c["legs"],1):
            lines.append(f"| {i} | {x['home']} - {x['away']} | {x['market']} | {x['odds']:.2f} | {x['model_probability_pct']:.2f}% | {x['value_edge_pct']:+.2f}% | {x['ev_pct']:+.2f}% | {x['engine_consensus']} |")
        lines += ["",f"**Combined decimal odds:** {c['combined_decimal_odds']}"]
    else: lines.append("**NO BET:** Quality/value gates produced no qualifying leg.")
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--snapshot",default="data/footystats_snapshot.json")
    args=p.parse_args();print(json.dumps(run(args.snapshot)["coupon"],ensure_ascii=False,indent=2))
