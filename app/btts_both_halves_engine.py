"""Special market: BTTS in BOTH halves (1H BTTS YES + 2H BTTS YES)."""
from __future__ import annotations
from footystats_parser import parse_snapshot

MIN_ODDS=1.80
MIN_HALF_PROB=.20
MAX_ODDS=12.0

def analyze_btts_both_halves(matches):
    results=[]
    for m in matches:
        p1=m.get("btts_1h_rate")
        p2=m.get("btts_2h_rate")
        if p1 is None or p2 is None or p1 < MIN_HALF_PROB or p2 < MIN_HALF_PROB:
            continue
        # Independence approximation is deliberately conservative; apply correlation haircut.
        raw=p1*p2
        probability=raw*0.90
        odds=m.get("odds",{}).get("btts_both_halves")
        # Snapshot may not expose this bookmaker market yet. Still rank candidates statistically.
        implied=(1/odds) if odds and MIN_ODDS<=odds<=MAX_ODDS else None
        edge=(probability-implied) if implied else None
        score=round(min(10, probability*18 + min(p1,p2)*3),1)
        results.append({**m,
          "market":"1H BTTS YES + 2H BTTS YES",
          "probability":round(probability*100,1),
          "p_1h":round(p1*100,1),"p_2h":round(p2*100,1),
          "odds_value":odds,
          "implied_probability":round(implied*100,1) if implied else None,
          "value_edge":round(edge*100,1) if edge is not None else None,
          "confidence_10":score,
          "status":"CANDIDATE - ODDS VERIFY" if odds is None else ("ANALYZE" if edge and edge>=.03 else "NO VALUE")
        })
    return sorted(results,key=lambda x:(x["confidence_10"],x["probability"]),reverse=True)

if __name__=="__main__":
    r=analyze_btts_both_halves(parse_snapshot())
    print(f"BOTH-HALVES BTTS CANDIDATES: {len(r)}")
    for i,x in enumerate(r[:20],1):
        odds=f" @ {x['odds_value']:.2f}" if x['odds_value'] else ""
        print(f"#{i} {x['home']} - {x['away']} | {x['market']}{odds} | 1H={x['p_1h']}% | 2H={x['p_2h']}% | COMBINED={x['probability']}% | confidence={x['confidence_10']}/10 | {x['status']}")
