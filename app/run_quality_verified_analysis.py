"""Strict quality selection layer."""
from __future__ import annotations
from footystats_parser import parse_snapshot
from footystats_engine import analyze

DEV_WORDS=(" U19"," U20"," U21"," RESERVE"," WOMEN"," FEMALE")
SECOND_WORDS=(" II",)

def is_dev(m):
    t=(" "+m.get("league","")+" "+m.get("home","")+" "+m.get("away","")).upper()
    return any(w in t for w in DEV_WORDS), any(w in t for w in SECOND_WORDS)

def model_probability(m):
    hx,ax=m.get("home_xg"),m.get("away_xg")
    if hx is None or ax is None:return None
    if m["market"]=="BTTS YES":
        return max(.15,min(.85,(1-2.71828**(-hx))*(1-2.71828**(-ax))))
    target={"OVER 1.5":1.5,"OVER 2.5":2.5,"OVER 3.5":3.5}.get(m["market"])
    return None if target is None else max(.05,min(.90,(hx+ax)/(hx+ax+target)))

def run():
    finalists=[]
    for m in analyze(parse_snapshot()):
        fs=m["footystats_probability"]/100; model=model_probability(m)
        if model is None: continue
        gap=abs(fs-model); implied=m["implied_probability"]/100
        final=.55*fs+.45*model; edge=final-implied
        dev,second=is_dev(m)
        # Strict calibration: >20pp disagreement rejected; extreme edge flagged out.
        if gap>.20 or edge<.05 or edge>.25 or final<.55: continue
        agreement=1-gap
        conf=10*(.40*final+.30*agreement+.20*min(edge/.20,1)+.10)
        cap=6.5 if dev else (7.0 if second else 8.5)
        conf=round(min(cap,conf),1)
        finalists.append({**m,"model_probability":round(model*100,1),
          "final_probability":round(final*100,1),"final_edge":round(edge*100,1),
          "model_gap":round(gap*100,1),"final_confidence":conf,
          "risk":"DEV" if dev else ("SECOND_TEAM" if second else "NORMAL")})
    finalists.sort(key=lambda x:(x["final_confidence"],x["final_edge"]),reverse=True)
    print(f"RAW VALUE CANDIDATES: {len(analyze(parse_snapshot()))}")
    print(f"STRICT FINALISTS: {len(finalists)}")
    for n,x in enumerate(finalists[:5],1):
        print(f"#{n} {x['home']} - {x['away']} | {x['market']} @ {x['odds_value']:.2f} | FS={x['footystats_probability']}% | MODEL={x['model_probability']}% | FINAL={x['final_probability']}% | edge=+{x['final_edge']}% | gap={x['model_gap']}% | risk={x['risk']} | confidence={x['final_confidence']}/10")
if __name__=="__main__": run()
