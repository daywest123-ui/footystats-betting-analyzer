"""FootyStats-specific market probabilities and candidate generation."""
from __future__ import annotations

MIN_ODDS=1.55
def clamp(x): return max(.01,min(.99,x))
def analyze(matches):
    out=[]
    for m in matches:
        o=m["odds"]; candidates=[
          ("BTTS YES",m.get("btts_rate"),o.get("btts_yes")),
          ("OVER 1.5",m.get("over_15_rate"),o.get("over_15")),
          ("OVER 2.5",m.get("over_25_rate"),o.get("over_25")),
          ("OVER 3.5",m.get("over_35_rate"),o.get("over_35")),
          ("OVER 9.5 CORNERS",None,o.get("over_95_corners")),
        ]
        for market,p,odds in candidates:
            if not odds or odds < MIN_ODDS or not p: continue
            implied=1/odds
            edge=p-implied
            if edge <= 0: continue
            confidence=round(min(10, max(0, 5 + edge*25 + min(.8,p)*2)),1)
            out.append({**m,"market":market,"odds_value":odds,
                        "footystats_probability":round(p*100,1),
                        "implied_probability":round(implied*100,1),
                        "value_edge":round(edge*100,1),
                        "confidence_10":confidence,"decision":"ANALYZE"})
    return sorted(out,key=lambda x:(x["confidence_10"],x["value_edge"]),reverse=True)
