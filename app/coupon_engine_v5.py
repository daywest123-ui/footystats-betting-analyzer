"""Transparent multi-market coupon construction. Analysis only; never places bets."""
from __future__ import annotations
from math import prod
from typing import Any
from app.value_engine import implied_probability
from app.advanced_market_engine import no_vig_three_way

MIN_PROBABILITY=.55
MIN_EDGE=.025
MIN_EV=.03
MIN_DATA_QUALITY=.65
MAX_LEGS=4
MIN_ODDS=1.50
MAX_ODDS=4.50
MARKETS=("home_win","draw","away_win","btts_yes","btts_no",
         "over_0_5","over_1_5","over_2_5","over_3_5",
         "under_0_5","under_1_5","under_2_5","under_3_5",
         "over_85_corners","over_95_corners","over_105_corners",
         "btts_1h_yes","btts_2h_yes")

def build_candidates(fixtures:list[dict[str,Any]],*,max_candidates=20)->list[dict[str,Any]]:
    candidates=[]
    for f in fixtures:
        for market in MARKETS:
            fused=f.get("fusion",{}).get(market)
            odds=f.get("odds",{}).get(market)
            if not fused or odds is None: continue
            odds=float(odds)
            if not MIN_ODDS<=odds<=MAX_ODDS: continue
            p=float(fused["probability"])
            implied=implied_probability(odds)
            edge=p-implied
            ev=p*odds-1
            if p<MIN_PROBABILITY or edge<MIN_EDGE or ev<MIN_EV: continue
            quality=float(fused.get("data_quality",0))
            if quality<MIN_DATA_QUALITY: continue
            engines=int(fused.get("engine_count",0))
            agreement=int(fused.get("agreement",0))
            if engines<3 or agreement<max(2,engines-1): continue

            # Anti-false-value gate: a large model/market disagreement is only
            # accepted when the underlying data quality is unusually strong.
            market_prob = None
            market_gap = 0.0
            if market in ("home_win", "draw", "away_win"):
                mp = no_vig_three_way(f.get("odds", {}))
                market_prob = mp.get(market)
                if market_prob is not None:
                    market_gap = abs(p - market_prob)
                    if market_gap > 0.20 and quality < 0.85:
                        continue

            # xG contradiction is a warning, not an automatic rejection.
            xg_diff = fused.get("xg_diff")
            xg_conflict = 0.0
            try:
                if xg_diff is not None:
                    if market == "home_win" and float(xg_diff) < -0.35:
                        xg_conflict = min(1.0, abs(float(xg_diff)) / 1.5)
                    elif market == "away_win" and float(xg_diff) > 0.35:
                        xg_conflict = min(1.0, abs(float(xg_diff)) / 1.5)
                    elif market == "draw" and abs(float(xg_diff)) > 0.60:
                        xg_conflict = min(1.0, abs(float(xg_diff)) / 1.5)
            except (TypeError, ValueError):
                xg_conflict = 0.0
            fixture_id=f.get("fixture_id") or f"{f.get('home')}|{f.get('away')}|{f.get('fixture_date')}"
            candidates.append({
                "fixture_id":fixture_id,"home":f.get("home"),"away":f.get("away"),
                "league":f.get("league"),"market":market,"odds":round(odds,2),
                "model_probability_pct":round(p*100,2),
                "implied_probability_pct":round(implied*100,2),
                "value_edge_pct":round(edge*100,2),"ev_pct":round(ev*100,2),
                "data_quality":round(quality,3),"engine_consensus":f"{agreement}/{engines}",
                "market_probability_pct":round(market_prob*100,2) if market_prob is not None else None,
                "market_gap_pct":round(market_gap*100,2),
                "xg_conflict":round(xg_conflict,3),
                "score":round(ev*100+edge*60+p*10+quality*5-market_gap*35-xg_conflict*8,3),
                "votes":fused.get("votes",[])
            })
    return sorted(candidates,key=lambda x:x["score"],reverse=True)[:max_candidates]

def build_coupon(candidates,max_legs=MAX_LEGS)->dict[str,Any]:
    selected=[]; used_fixtures=set(); used_market_types=set()
    for c in candidates:
        fixture=str(c["fixture_id"])
        if fixture in used_fixtures: continue
        # Avoid a coupon dominated by one market family.
        family=("RESULT" if c["market"] in ("home_win","draw","away_win") else
                "GOALS" if c["market"].startswith(("over_","under_")) and "corners" not in c["market"] else
                "CORNERS" if "corners" in c["market"] else "BTTS")
        if family in used_market_types and len(selected)<2: continue
        selected.append(c); used_fixtures.add(fixture); used_market_types.add(family)
        if len(selected)>=max_legs: break
    combined=prod(float(x["odds"]) for x in selected) if selected else 0
    return {"status":"COUPON_CANDIDATES" if selected else "NO_BET",
            "legs":selected,"leg_count":len(selected),
            "combined_decimal_odds":round(combined,2) if selected else None,
            "selection_rule":"one market per fixture; diversified market families; no forced leg"}
