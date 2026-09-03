"""Cross-engine verification for FootyStats value candidates.

FootyStats is used as a candidate generator, not as the final authority.
A candidate is eligible only after independent form/model confirmation.
"""
from __future__ import annotations
from footystats_parser import parse_snapshot
from footystats_engine import analyze

def _form_proxy(m):
    # Conservative independent proxy from xG and goal environment.
    hx, ax = m.get("home_xg"), m.get("away_xg")
    if hx is None or ax is None: return None
    total = hx + ax
    if m["market"] == "BTTS YES":
        return min(.85, max(.25, (min(hx,2.2)/2.2)*.55 + min(ax,2.2)/2.2*.45))
    if m["market"] == "OVER 1.5": return min(.90, max(.20, total/3.2))
    if m["market"] == "OVER 2.5": return min(.85, max(.10, total/4.0))
    if m["market"] == "OVER 3.5": return min(.70, max(.05, total/5.0))
    return None

def run():
    candidates = analyze(parse_snapshot())
    final=[]
    for m in candidates:
        fs=m["footystats_probability"]/100
        form=_form_proxy(m)
        if form is None: continue
        # Independent confirmation must not diverge materially from FootyStats.
        if abs(fs-form) > .22: continue
        model=(fs+form)/2
        implied=m["implied_probability"]/100
        edge=model-implied
        if edge < .04: continue
        consensus=2 if abs(fs-form)<=.12 else 1
        if consensus < 2: continue
        confidence=min(8.5, round(5.0 + edge*12 + consensus*.7,1))
        final.append({**m,"form_probability":round(form*100,1),
                      "final_probability":round(model*100,1),
                      "final_edge":round(edge*100,1),
                      "consensus":f"{consensus}/2",
                      "final_confidence":confidence})
    final.sort(key=lambda x:(x["final_confidence"],x["final_edge"]),reverse=True)
    print(f"FOOTYSTATS CANDIDATES: {len(candidates)}")
    print(f"CROSS-VERIFIED FINALISTS: {len(final)}")
    for n,x in enumerate(final[:10],1):
        print(f"#{n} {x['home']} - {x['away']} | {x['market']} @ {x['odds_value']:.2f} | FS={x['footystats_probability']}% | FORM={x['form_probability']}% | FINAL={x['final_probability']}% | edge=+{x['final_edge']}% | consensus={x['consensus']} | confidence={x['final_confidence']}/10")
if __name__=="__main__":
    run()
