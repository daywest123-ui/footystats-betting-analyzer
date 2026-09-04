"""Quality-aware final selection layer.

This module intentionally penalizes low-liquidity/development fixtures and avoids
calling a derived xG proxy an independent consensus source.
"""
from __future__ import annotations
from footystats_parser import parse_snapshot
from footystats_engine import analyze

RISK_WORDS=(" U19"," U20"," U21"," II"," RESERVE"," WOMEN"," FEMALE")

def fixture_risk(m):
    text=(m.get("league","")+" "+m.get("home","")+" "+m.get("away","")).upper()
    return .18 if any(w in text for w in RISK_WORDS) else 0.0

def poisson_like(m):
    hx,ax=m.get("home_xg"),m.get("away_xg")
    if hx is None or ax is None: return None
    total=hx+ax
    market=m["market"]
    if market=="BTTS YES":
        return max(.15,min(.85,(1-2.71828**(-hx))*(1-2.71828**(-ax))))
    targets={"OVER 1.5":1.5,"OVER 2.5":2.5,"OVER 3.5":3.5}
    if market in targets:
        # conservative monotonic approximation; not presented as exact Poisson CDF
        return max(.05,min(.90,total/(total+targets[market])))
    return None

def score(m):
    fs=m["footystats_probability"]/100
    model=poisson_like(m)
    if model is None: return None
    implied=m["implied_probability"]/100
    agreement=1-abs(fs-model)
    final=.55*fs+.45*model
    edge=final-implied
    risk=fixture_risk(m)
    quality=max(0,1-risk)
    if edge < .035 or final < .52 or agreement < .72: return None
    confidence=10*(.35*final+.25*agreement+.25*min(edge/.20,1)+.15*quality)
    confidence=min(8.8,round(confidence,1))
    return {**m,"model_probability":round(model*100,1),
            "final_probability":round(final*100,1),
            "final_edge":round(edge*100,1),
            "agreement":round(agreement*100,1),
            "risk_penalty":round(risk*100,1),
            "final_confidence":confidence}

def run():
    raw=analyze(parse_snapshot())
    finalists=[x for m in raw if (x:=score(m))]
    finalists.sort(key=lambda x:(x["final_confidence"],x["final_edge"]),reverse=True)
    print(f"RAW VALUE CANDIDATES: {len(raw)}")
    print(f"QUALITY-VERIFIED FINALISTS: {len(finalists)}")
    for n,x in enumerate(finalists[:5],1):
        print(f"#{n} {x['home']} - {x['away']} | {x['market']} @ {x['odds_value']:.2f} | FS={x['footystats_probability']}% | MODEL={x['model_probability']}% | FINAL={x['final_probability']}% | edge=+{x['final_edge']}% | agreement={x['agreement']}% | risk=-{x['risk_penalty']}% | confidence={x['final_confidence']}/10")
if __name__=="__main__":
    run()
