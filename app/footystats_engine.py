"""FootyStats-specific market probabilities and candidate generation."""
from __future__ import annotations

MIN_ODDS=1.55
MAX_ODDS=4.50
MAX_EDGE=0.30  # extreme edges are usually stale/misaligned odds and require manual verification
MIN_PROB=0.48
def clamp(x): return max(.01,min(.99,x))
def analyze(matches):
    out=[]
    # Conservative sanity filters: do not treat implausible odds/edge gaps as automatic value.
    for m in matches:
        o=m["odds"]; candidates=[
          ("BTTS YES",m.get("btts_rate"),o.get("btts_yes")),
          ("OVER 1.5",m.get("over_15_rate"),o.get("over_15")),
          ("OVER 2.5",m.get("over_25_rate"),o.get("over_25")),
          ("OVER 3.5",m.get("over_35_rate"),o.get("over_35")),
          ("OVER 9.5 CORNERS",None,o.get("over_95_corners")),
        ]
        for market,p,odds in candidates:
            if not odds or odds < MIN_ODDS or odds > MAX_ODDS or not p or p < MIN_PROB: continue
            implied=1/odds
            edge=p-implied
            if edge <= 0 or edge > MAX_EDGE: continue
            confidence=round(min(10, max(0, 5 + edge*25 + min(.8,p)*2)),1)
            out.append({**m,"market":market,"odds_value":odds,
                        "footystats_probability":round(p*100,1),
                        "implied_probability":round(implied*100,1),
                        "value_edge":round(edge*100,1),
                        "confidence_10":confidence,"decision":"ANALYZE"})
    return sorted(out,key=lambda x:(x["confidence_10"],x["value_edge"]),reverse=True)
