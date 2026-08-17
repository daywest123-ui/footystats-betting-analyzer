"""Evidence-gated multi-sport coupon scanner.
API-Sports supplies fixture discovery; The Odds API supplies current bookmaker odds.
No coupon is emitted without real current odds.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
import requests

API_KEY=os.getenv("API_FOOTBALL_KEY","").strip()
ODDS_KEY=os.getenv("THE_ODDS_API_KEY","").strip()
TIMEOUT=20
HEAD={"Accept":"application/json","User-Agent":"Mozilla/5.0"}
SPORTS={
 "football":{"base":"https://v3.football.api-sports.io","endpoint":"fixtures"},
 "basketball":{"base":"https://v1.basketball.api-sports.io","endpoint":"games"},
 "volleyball":{"base":"https://v1.volleyball.api-sports.io","endpoint":"games"},
 "hockey":{"base":"https://v1.hockey.api-sports.io","endpoint":"games"},
}

def get(url,params,headers):
 r=requests.get(url,params=params,headers=headers,timeout=TIMEOUT); r.raise_for_status(); d=r.json()
 if d.get("errors"): raise RuntimeError(str(d["errors"]))
 return d

def api_fixtures(sport,day):
 if not API_KEY: return []
 c=SPORTS[sport]
 d=get(f"{c['base']}/{c['endpoint']}",{"date":day},{**HEAD,"x-apisports-key":API_KEY})
 out=[]
 for x in d.get("response") or []:
  t=x.get("teams") or {}; h=(t.get("home") or {}).get("name"); a=(t.get("away") or {}).get("name")
  if not h or not a: continue
  f=x.get("fixture") or x.get("game") or {}; st=(f.get("status") or {}).get("short") or ""
  if str(st).lower() in {"ft","finished","final","aet","pen","canceled","cancelled","postponed"}: continue
  out.append({"sport":sport,"home":h,"away":a,"league":(x.get("league") or {}).get("name"),"id":f.get("id") or f.get("game_id")})
 return out

def odds_sports():
 return get("https://api.the-odds-api.com/v4/sports/",{"apiKey":ODDS_KEY},HEAD) if ODDS_KEY else []

def odds_events(key):
 return get(f"https://api.the-odds-api.com/v4/sports/{key}/odds/",{"apiKey":ODDS_KEY,"regions":"eu","markets":"h2h,spreads,totals","oddsFormat":"decimal"},HEAD)

def classify(s):
 q=f"{s.get('title','')} {s.get('group','')} {s.get('key','')}".lower()
 if "volleyball" in q:return "volleyball"
 if "basketball" in q:return "basketball"
 if "hockey" in q:return "hockey"
 if "soccer" in q or "football" in q:return "football"
 return None

def sim(a,b): return SequenceMatcher(None,"".join(c.lower() if c.isalnum() else " " for c in a),"".join(c.lower() if c.isalnum() else " " for c in b)).ratio()

def matches(e,fixtures):
 return any(sim(e.get("home_team","") ,f["home"])>=.55 and sim(e.get("away_team","") ,f["away"])>=.55 for f in fixtures)

def candidates(e,sport):
 out=[]
 for b in e.get("bookmakers") or []:
  for m in b.get("markets") or []:
   if m.get("key") not in {"h2h","spreads","totals"}: continue
   for o in m.get("outcomes") or []:
    try: odd=float(o.get("price"))
    except: continue
    if not 1.20<=odd<=8: continue
    out.append({"sport":sport,"event_id":e.get("id"),"home":e.get("home_team"),"away":e.get("away_team"),"commence_time":e.get("commence_time"),"pick":o.get("name"),"market":m.get("key"),"odd":round(odd,2),"implied_probability":round(1/odd,4),"bookmaker":b.get("title") or b.get("key")})
 return out

def coupons(cs):
 best={}
 for c in cs:
  k=(c["sport"],c["event_id"],c["pick"],c["market"])
  if k not in best or c["odd"]>best[k]["odd"]: best[k]=c
 cs=list(best.values())
 balanced=[]; used=set()
 for c in sorted(cs,key=lambda x:(-x["implied_probability"],x["odd"])):
  if c["event_id"] in used: continue
  balanced.append({**c,"risk":"medium"}); used.add(c["event_id"])
  if len(balanced)==4: break
 surprise=[]; bu={x["event_id"] for x in balanced}
 for c in sorted(cs,key=lambda x:(-x["odd"],-x["implied_probability"])):
  if c["event_id"] in bu: continue
  surprise.append({**c,"risk":"high"})
  if len(surprise)==4: break
 return {"conservative_mixed":balanced,"surprise_mixed":surprise,"eligible_candidates":len(cs),"status":"READY_FOR_MANUAL_CHECK" if (balanced or surprise) else "NO_BET","reason":None if (balanced or surprise) else "No current bookmaker odds available."}

def main():
 day=datetime.now(timezone.utc).strftime("%Y-%m-%d")
 report={"date_utc":day,"api_sports_key_configured":bool(API_KEY),"odds_api_key_configured":bool(ODDS_KEY),"api_sports_fixtures_by_sport":{},"odds_api_sports_checked":[],"odds_api_events_by_sport":{},"errors":{}}
 fixtures={}
 for sport in SPORTS:
  try: fixtures[sport]=api_fixtures(sport,day)[:6]; report["api_sports_fixtures_by_sport"][sport]=len(fixtures[sport])
  except Exception as e: fixtures[sport]=[]; report["api_sports_fixtures_by_sport"][sport]=0; report["errors"][f"api_{sport}"]=f"{type(e).__name__}: {e}"
 cs=[]
 if not ODDS_KEY: report["errors"]["odds_api"]="THE_ODDS_API_KEY secret is missing"
 else:
  try:
   wanted=[]
   for s in odds_sports():
    sport=classify(s)
    if sport and sport not in {x[0] for x in wanted}: wanted.append((sport,s["key"],s.get("title")))
   for sport,key,title in wanted[:4]:
    report["odds_api_sports_checked"].append({"sport":sport,"key":key,"title":title})
    try:
     ev=odds_events(key); report["odds_api_events_by_sport"][sport]=len(ev)
     for e in ev:
      if matches(e,fixtures.get(sport,[])) or not fixtures.get(sport): cs.extend(candidates(e,sport))
    except Exception as e: report["errors"][f"odds_{sport}"]=f"{type(e).__name__}: {e}"
  except Exception as e: report["errors"]["odds_sports"]=f"{type(e).__name__}: {e}"
 report["coupons"]=coupons(cs)
 Path("reports").mkdir(exist_ok=True); Path("reports/multi_sport_coupon.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
