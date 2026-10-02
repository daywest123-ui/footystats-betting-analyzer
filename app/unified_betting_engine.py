"""Unified football betting analysis core.
Integrates the existing FOUR-ENGINE, open-source intelligence, HT/FT, exact-score,
market and coupon layers. Analysis only: never places bets.
"""
from __future__ import annotations
from collections import Counter
from math import isfinite
from typing import Any

HTFT=("1/1","1/X","1/2","X/1","X/X","X/2","2/1","2/X","2/2")

def _safe_float(v):
    try:
        x=float(v); return x if isfinite(x) else None
    except (TypeError,ValueError): return None

def _normalize(probs, alpha=1.0):
    vals={k:max(0.0,float(probs.get(k,0.0)))+alpha for k in HTFT}
    total=sum(vals.values())
    return {k:vals[k]/total for k in HTFT}

def _weighted_average(a,b,wa=.5,wb=.5):
    out={k:wa*a.get(k,0.0)+wb*b.get(k,0.0) for k in HTFT}
    total=sum(out.values())
    return {k:out[k]/total for k in HTFT} if total else _normalize(out)

def _team_id(name):
    from app.open_source_intel import _find_team
    return _find_team(name)

def _htft_distribution(rows):
    counts=Counter(f"{r['ht']}/{r['ft']}" for r in rows
                   if r.get("ht") in {"1","X","2"} and r.get("ft") in {"1","X","2"})
    return _normalize({k:float(counts.get(k,0)) for k in HTFT})

def _score_distribution(rows, team_is_home):
    counts=Counter(); valid=0
    for r in rows:
        try: hg,ag=int(r["hg"]),int(r["ag"])
        except (KeyError,TypeError,ValueError): continue
        gf,ga=(hg,ag) if team_is_home else (ag,hg)
        counts[f"{gf}-{ga}"]+=1; valid+=1
    return {k:v/valid for k,v in counts.items()} if valid else {}

def _merge_score_baselines(a,b):
    keys=set(a)|set(b)
    raw={k:.5*a.get(k,0.0)+.5*b.get(k,0.0) for k in keys}
    total=sum(raw.values())
    return dict(sorted(((k,v/total) for k,v in raw.items()),key=lambda x:x[1],reverse=True)) if total else {}

def _no_vig_1x2(odds):
    if not odds: return {}
    mapping={"home_win":"1","draw":"X","away_win":"2"}; inv={}
    for market,label in mapping.items():
        o=_safe_float(odds.get(market))
        if o and o>1: inv[label]=1/o
    total=sum(inv.values())
    return {k:v/total for k,v in inv.items()} if total else {}

def _risk(htft,sample):
    top=max(htft.values()) if htft else 0
    second=sorted(htft.values(),reverse=True)[1] if len(htft)>1 else 0
    spread=top-second
    draw=sum(v for k,v in htft.items() if k.startswith("X/") or k.endswith("/X"))
    if sample<12 or top<.18 or spread<.025: return "HIGH"
    if draw>=.42 or spread<.06: return "MEDIUM"
    return "LOW"

def analyze_htft(home,away,recent_limit=30,odds=None):
    try:
        hid,hs=_team_id(home); aid,ass=_team_id(away)
        if hid is None or aid is None:
            return {"status":"UNAVAILABLE","reason":f"{hs}; {ass}","probabilities":{}}
        from app.open_source_intel import _extract_match,_team_rows
        hrows=[x for x in (_extract_match(r,home) for r in _team_rows(hid,recent_limit)) if x]
        arows=[x for x in (_extract_match(r,away) for r in _team_rows(aid,recent_limit)) if x]
        probs=_weighted_average(_htft_distribution(hrows),_htft_distribution(arows))
        h2h=[]
        for r in hrows:
            if away.lower() in (r["home"].lower(),r["away"].lower()): h2h.append(r)
        for r in arows:
            if home.lower() in (r["home"].lower(),r["away"].lower()) and r not in h2h: h2h.append(r)
        if h2h: probs=_weighted_average(probs,_htft_distribution(h2h),.85,.15)
        return {
            "status":"OK","method":"historical_HTFT_ensemble","home":home,"away":away,
            "sample":{"home_history":len(hrows),"away_history":len(arows),"h2h":len(h2h)},
            "probabilities":{k:round(probs[k],6) for k in HTFT},
            "probability_pct":{k:round(probs[k]*100,2) for k in HTFT},
            "fair_odds":{k:round(1/probs[k],2) for k in HTFT if probs[k]>0},
            "market_1x2_no_vig":_no_vig_1x2(odds),
            "risk":_risk(probs,min(len(hrows),len(arows))),
            "data_quality":round(min(1.0,min(len(hrows),len(arows))/30),3)
        }
    except Exception as exc:
        return {"status":"ERROR","error":f"{type(exc).__name__}: {exc}","probabilities":{}}

def exact_score_baseline(home,away,recent_limit=30,top_n=10):
    try:
        hid,hs=_team_id(home); aid,ass=_team_id(away)
        if hid is None or aid is None: return {"status":"UNAVAILABLE","reason":f"{hs}; {ass}"}
        from app.open_source_intel import _extract_match,_team_rows
        hrows=[x for x in (_extract_match(r,home) for r in _team_rows(hid,recent_limit)) if x]
        arows=[x for x in (_extract_match(r,away) for r in _team_rows(aid,recent_limit)) if x]
        merged=_merge_score_baselines(_score_distribution(hrows,True),_score_distribution(arows,False))
        return {"status":"OK","method":"historical_score_baseline",
                "sample":{"home":len(hrows),"away":len(arows)},
                "top_scores":[{"score":k,"probability_pct":round(v*100,2),"fair_odds":round(1/v,2)}
                              for k,v in list(merged.items())[:top_n]]}
    except Exception as exc:
        return {"status":"ERROR","error":f"{type(exc).__name__}: {exc}"}

def analyze_match_bundle(home,away,odds=None,snapshot=None,recent_limit=30):
    result={"home":home,"away":away,"components":{},"decision":{"status":"ANALYSIS_ONLY"}}
    result["components"]["htft"]=analyze_htft(home,away,recent_limit,odds)
    result["components"]["exact_score"]=exact_score_baseline(home,away,recent_limit)
    result["components"]["market"]={"odds_available":bool(odds),"no_vig_1x2":_no_vig_1x2(odds)}
    if snapshot is not None:
        try:
            from app.four_engine_fusion import fuse_market
            from app.open_source_intel import analyze_match
            fusion={}
            for market,price in (odds or {}).items():
                if price is None: continue
                try: fusion[market]=fuse_market(market,snapshot,price,None)
                except Exception: pass
            result["components"]["four_engine"]=fusion
            result["components"]["open_source_intel"]=analyze_match(home,away)
        except Exception as exc:
            result["components"]["four_engine_status"]={"status":"UNAVAILABLE","error":f"{type(exc).__name__}: {exc}"}
    return result

def select_htft_candidates(analyses,min_probability=.12,max_candidates=8):
    rows=[]; rank={"LOW":0,"MEDIUM":1,"HIGH":2}
    for a in analyses:
        c=a.get("components",{}).get("htft",{})
        for outcome,p in c.get("probabilities",{}).items():
            if p<min_probability: continue
            rows.append({"home":a.get("home"),"away":a.get("away"),
                         "market":f"HT/FT {outcome}","probability_pct":round(p*100,2),
                         "fair_odds":c.get("fair_odds",{}).get(outcome),"risk":c.get("risk"),
                         "sample":c.get("sample"),"data_quality":c.get("data_quality")})
    return sorted(rows,key=lambda x:(-x["probability_pct"],rank.get(x["risk"],3)))[:max_candidates]
