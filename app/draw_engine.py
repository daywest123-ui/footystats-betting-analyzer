"""Draw-market scanner: conservative candidates, not automatic picks."""
from __future__ import annotations
from footystats_parser import parse_snapshot

MIN_DRAW_ODDS=2.80
MAX_DRAW_ODDS=3.30
MAX_FORM_GAP=.45
MIN_AVG=.9
MAX_AVG=3.2

def draw_score(m):
    odds=m.get("odds",{}).get("draw")
    if not odds or not MIN_DRAW_ODDS<=odds<=MAX_DRAW_ODDS:return None
    # Snapshot currently stores team-level home/away form at numeric positions 0/1
    # if parser schema exposes them; fall back to xG balance.
    hx,ax=m.get("home_xg"),m.get("away_xg")
    if hx is None or ax is None:return None
    avg=m.get("avg_goals")
    if avg is not None and not MIN_AVG<=avg<=MAX_AVG:return None
    xg_gap=abs(hx-ax)
    if xg_gap>0.55:return None
    # Balanced sides + moderate goal environment + central draw price.
    price_center=1-abs(odds-3.05)/.25
    balance=1-xg_gap/.55
    goal_fit=1 if avg is None else max(0,1-abs(avg-2.2)/1.3)
    score=100*(.45*balance+.30*price_center+.25*goal_fit)
    if score<60:return None
    return {"draw_odds":odds,"xg_gap":round(xg_gap,2),
            "draw_score":round(score,1),"decision":"DRAW_CANDIDATE"}

def run():
    rows=[]
    for m in parse_snapshot():
        r=draw_score(m)
        if r: rows.append({**m,**r})
    rows.sort(key=lambda x:x["draw_score"],reverse=True)
    print(f"DRAW ODDS BAND: {MIN_DRAW_ODDS:.2f}-{MAX_DRAW_ODDS:.2f}")
    print(f"BALANCED DRAW CANDIDATES: {len(rows)}")
    for n,x in enumerate(rows[:10],1):
        print(f"#{n} {x['home']} - {x['away']} | DRAW @ {x['draw_odds']:.2f} | xG gap={x['xg_gap']} | AVG={x.get('avg_goals')} | score={x['draw_score']}/100")
if __name__=="__main__":run()
