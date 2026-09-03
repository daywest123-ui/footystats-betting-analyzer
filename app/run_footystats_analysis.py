from footystats_parser import parse_snapshot
from footystats_engine import analyze
m=parse_snapshot()
r=analyze(m)
print(f"FOOTYSTATS MATCHES PARSED: {len(m)}")
print(f"VALUE CANDIDATES: {len(r)}")
for n,x in enumerate(r[:15],1):
 print(f"#{n} {x['home']} - {x['away']} | {x['market']} @ {x['odds_value']:.2f} | FS={x['footystats_probability']}% | implied={x['implied_probability']}% | edge=+{x['value_edge']}% | confidence={x['confidence_10']}/10")
