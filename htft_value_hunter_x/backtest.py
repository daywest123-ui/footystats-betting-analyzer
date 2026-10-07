import argparse,pandas as pd
from engine import analyze,HTFT

def actual(r):
    h1,a1=float(r.ht_home),float(r.ht_away)
    hf,af=float(r.ft_home),float(r.ft_away)
    ht="1" if h1>a1 else "X" if h1==a1 else "2"
    ft="1" if hf>af else "X" if hf==af else "2"
    return f"{ht}/{ft}"

def mean_or(values,fallback):
    return sum(values)/len(values) if values else fallback

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="htft_value_hunter_x/data/matches.csv")
    args=ap.parse_args()
    df=pd.read_csv(args.input).sort_values("date").reset_index(drop=True)
    required={"date","home","away","ht_home","ht_away","ft_home","ft_away"}
    missing=required-set(df.columns)
    if missing: raise SystemExit(f"Eksik kolonlar: {sorted(missing)}")
    hist={}; league=[]
    rows=[]
    for _,r in df.iterrows():
        H,A=str(r.home),str(r.away)
        hh=hist.get(H,{"gf":[],"ga":[]}); aa=hist.get(A,{"gf":[],"ga":[]})
        lg=mean_or(league,1.35)
        lh=max(.15,(mean_or(hh["gf"],lg)+mean_or(aa["ga"],lg))/2)
        la=max(.15,(mean_or(aa["gf"],lg)+mean_or(hh["ga"],lg))/2)
        res=analyze(H,A,lh,la)
        probs={x["market"]:x["probability"] for x in res["htft"]}
        act=actual(r); pred=max(probs,key=probs.get)
        brier=sum((probs[k]-(1 if k==act else 0))**2 for k in HTFT)
        rows.append({"date":r.date,"home":H,"away":A,"actual":act,"pred":pred,"hit":int(pred==act),"brier":brier})
        hf,af=float(r.ft_home),float(r.ft_away)
        hist.setdefault(H,{"gf":[],"ga":[]}); hist.setdefault(A,{"gf":[],"ga":[]})
        hist[H]["gf"].append(hf); hist[H]["ga"].append(af)
        hist[A]["gf"].append(af); hist[A]["ga"].append(hf)
        league.extend([hf,af])
    out=pd.DataFrame(rows); out.to_csv("htft_backtest_results.csv",index=False)
    print("Maç:",len(out))
    print("HT/FT isabeti: %.2f%%"%(out.hit.mean()*100 if len(out) else 0))
    print("Brier: %.5f"%(out.brier.mean() if len(out) else 0))

if __name__=="__main__": main()
