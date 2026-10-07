import math

HTFT=["1/1","1/X","1/2","X/1","X/X","X/2","2/1","2/X","2/2"]

def poisson_pmf(k,lam):
    return math.exp(-lam)*lam**k/math.factorial(k)

def normalize(d):
    s=sum(d.values())
    return {k:v/s for k,v in d.items()} if s else d

def outcome_probs(lh,la,max_goals=8):
    hp=[poisson_pmf(i,lh) for i in range(max_goals+1)]
    ap=[poisson_pmf(i,la) for i in range(max_goals+1)]
    out={"1":0.0,"X":0.0,"2":0.0}
    for h,ph in enumerate(hp):
        for a,pa in enumerate(ap):
            out["1" if h>a else "X" if h==a else "2"]+=ph*pa
    return normalize(out)

def htft_probs(h1,a1,h2,a2,max_goals=7):
    out={k:0.0 for k in HTFT}
    hp1=[poisson_pmf(i,h1) for i in range(max_goals+1)]
    ap1=[poisson_pmf(i,a1) for i in range(max_goals+1)]
    hp2=[poisson_pmf(i,h2) for i in range(max_goals+1)]
    ap2=[poisson_pmf(i,a2) for i in range(max_goals+1)]
    for x,px in enumerate(hp1):
        for y,py in enumerate(ap1):
            ht="1" if x>y else "X" if x==y else "2"
            for u,pu in enumerate(hp2):
                for v,pv in enumerate(ap2):
                    ft="1" if x+u>y+v else "X" if x+u==y+v else "2"
                    out[f"{ht}/{ft}"]+=px*py*pu*pv
    return normalize(out)

def market_value(prob,odds):
    if prob<=0 or odds<=0:return None
    return {"fair_odds":1/prob,"implied_probability":1/odds,"value_pct":(odds*prob-1)*100}

def analyze(home,away,home_goals,away_goals,ht_share=.44,odds=None):
    h1=home_goals*ht_share; a1=away_goals*ht_share
    h2=home_goals*(1-ht_share); a2=away_goals*(1-ht_share)
    p=htft_probs(h1,a1,h2,a2)
    rows=[]
    for market,prob in p.items():
        row={"market":market,"probability":prob,"fair_odds":1/prob}
        if odds and market in odds:
            row["odds"]=odds[market]
            row.update(market_value(prob,odds[market]))
        rows.append(row)
    rows.sort(key=lambda x:x["probability"],reverse=True)
    return {"home":home,"away":away,"expected_goals":{"home":home_goals,"away":away_goals},"ht_result":outcome_probs(h1,a1),"ft_result":outcome_probs(home_goals,away_goals),"htft":rows}

if __name__=="__main__":
    import argparse,json
    p=argparse.ArgumentParser()
    p.add_argument("--home",required=True); p.add_argument("--away",required=True)
    p.add_argument("--home-goals",type=float,required=True); p.add_argument("--away-goals",type=float,required=True)
    a=p.parse_args()
    print(json.dumps(analyze(a.home,a.away,a.home_goals,a.away_goals),ensure_ascii=False,indent=2))
