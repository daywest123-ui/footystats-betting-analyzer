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
from app.coupon_engine_v5 import build_candidates,build_coupon,build_model_candidates,build_model_coupon,MARKETS
from app.open_source_intel import analyze_match as analyze_open_source_match
from app.external_prediction_sources import analyze_match as analyze_external_sources
from app.coupon_success_memory import market_stats as winning_coupon_memory_stats

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
        dc=dixon_coles_predict(matches,fixture["home"],fixture["away"],day)
        # IMPORTANT: odds are optional. The model must still analyze a fixture
        # when no bookmaker/FootyStats price is available.
        fusion={m:fuse_market(m,footystats=fs,home_form=hf,away_form=af,dixon_coles=dc)
                for m in MARKETS}
        enriched.append({**fixture,"odds":odds,"footystats":fs,"fusion":fusion})

    for item in enriched:
        try:
            item["external_prediction_sources"] = analyze_external_sources(item["home"],item["away"])
        except Exception as exc:
            item["external_prediction_sources"]={"status":"ERROR","sources":[],"consensus":[],
                "error":f"{type(exc).__name__}: {exc}"}

    candidates=build_candidates(enriched)
    coupon=build_coupon(candidates)
    model_candidates=build_model_candidates(enriched)
    model_coupon=build_model_coupon(model_candidates)

    for item in enriched:
        try:
            item["open_source_intel"]=analyze_open_source_match(item["home"],item["away"])
        except Exception as exc:
            item["open_source_intel"]={"status":"ERROR","error":f"{type(exc).__name__}: {exc}","opportunities":[]}
    special=[]
    for item in enriched:
        for opp in item.get("open_source_intel",{}).get("opportunities",[]):
            special.append({"home":item["home"],"away":item["away"],
                "fixture_date":item["fixture_date"],**opp})
    special.sort(key=lambda x:x.get("model_probability",0),reverse=True)

    report={"generated_at":now.isoformat(),"engine":"FOUR_ENGINE_COUPON_V3",
            "snapshot":snapshot_path,"fixtures_scanned":len(fixtures),
            "fixtures_enriched":len(enriched),
            "matches_with_odds":sum(1 for x in enriched if x.get("odds")),
            "candidate_count":len(candidates),
            "model_only_candidate_count":len(model_candidates),
            "candidate_markets":sorted({x["market"] for x in candidates}),
            "winning_coupon_memory":winning_coupon_memory_stats(),
            "model_only_markets":sorted({x["market"] for x in model_candidates}),
            "coupon":coupon,"model_only_coupon":model_coupon,
            "open_source_special_opportunities":special[:20],
            "external_prediction_sources":{
                f"{item['home']} - {item['away']}":item.get("external_prediction_sources",{})
                for item in enriched},
            "notes":[
                "Odds are optional for analysis. Missing odds no longer remove a fixture.",
                "Odds, when present, are used only for separate value/EV qualification.",
                "Model-only candidates use probability, fair odds, data quality and multi-engine agreement.",
                "No bookmaker price is invented; fair odds are 1/model_probability.",
                "One selection per fixture with market-family diversification.",
                "No leg is forced when model gates fail.",
                "DataFC/Sofascore supplies a separate historical HT/FT opportunity layer; H2H is secondary evidence.",
                "StatsBet, PitchDeep, xGaura, Predictions Footy and Kings Odds are evidence sources only.",
                "Probabilities are estimates, not guarantees."]}

    out=Path("reports");out.mkdir(exist_ok=True)
    (out/"latest_four_engine_coupon.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"latest_four_engine_coupon.md").write_text(render_markdown(report),encoding="utf-8")
    return report

def render_markdown(report):
    c=report["coupon"]; mc=report["model_only_coupon"]
    lines=["# FOUR-ENGINE FOOTYSTATS COUPON V3",f"- Generated: {report['generated_at']}",
           f"- Fixtures scanned: {report['fixtures_scanned']}",
           f"- Enriched: {report['fixtures_enriched']}",
           f"- With odds: {report['matches_with_odds']}",
           f"- Value candidates: {report['candidate_count']}",
           f"- Model-only candidates: {report['model_only_candidate_count']}",
           f"- Value status: {c['status']}",f"- Model-only status: {mc['status']}",""]
    if mc["legs"]:
        lines += ["## Model-only shortlist","| # | Match | Market | Model | Fair odds | Quality | Consensus |",
                  "|---:|---|---|---:|---:|---:|---:|"]
        for i,x in enumerate(mc["legs"],1):
            lines.append(f"| {i} | {x['home']} - {x['away']} | {x['market']} | {x['model_probability_pct']:.2f}% | {x['fair_odds']:.2f} | {x['data_quality']:.3f} | {x['engine_consensus']} |")
    else: lines.append("**MODEL-ONLY NO BET:** model gates produced no qualifying leg.")
    lines += [""]
    if c["legs"]:
        lines += ["## Value shortlist","| # | Match | Market | Odds | Model | Edge | EV | Consensus |",
                  "|---:|---|---|---:|---:|---:|---:|---|"]
        for i,x in enumerate(c["legs"],1):
            lines.append(f"| {i} | {x['home']} - {x['away']} | {x['market']} | {x['odds']:.2f} | {x['model_probability_pct']:.2f}% | {x['value_edge_pct']:+.2f}% | {x['ev_pct']:+.2f}% | {x['engine_consensus']} |")
    else: lines.append("**VALUE NO BET:** no qualifying leg with an actual price.")
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--snapshot",default="data/footystats_snapshot.json")
    args=p.parse_args();print(json.dumps(run(args.snapshot),ensure_ascii=False,indent=2))
