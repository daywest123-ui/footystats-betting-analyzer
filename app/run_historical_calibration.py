"""Leakage-safe walk-forward calibration using the production probability family."""
from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from statistics import mean

import requests

from app.calibration_backtest import CalibrationPoint, summarize

UA = "Mozilla/5.0 (compatible; FootballAnalyzerCalibration/1.0)"
TIMEOUT = 20
SEASONS = ("2526", "2425", "2324")
LEAGUES = {"E0":"England Premier League","D1":"Germany Bundesliga","SP1":"Spain La Liga","I1":"Italy Serie A","F1":"France Ligue 1","T1":"Turkey Super Lig"}
BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def _float(v):
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime((value or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def load_history():
    rows = []
    for season in SEASONS:
        for league, name in LEAGUES.items():
            try:
                r = requests.get(BASE.format(season=season, league=league),
                                 headers={"User-Agent": UA}, timeout=TIMEOUT)
                r.raise_for_status()
                data = list(csv.DictReader(io.StringIO(r.content.decode("cp1252", errors="replace"))))
            except requests.RequestException:
                continue
            for row in data:
                date = _parse_date(row.get("Date", ""))
                hg, ag = _float(row.get("FTHG")), _float(row.get("FTAG"))
                home, away = row.get("HomeTeam", "").strip(), row.get("AwayTeam", "").strip()
                if date is None or hg is None or ag is None or not home or not away:
                    continue
                rows.append({
                    "date":date,"home":home,"away":away,"hg":int(hg),"ag":int(ag),"league":name,
                    "odds":_float(row.get("B365H")),"odds_draw":_float(row.get("B365D")),
                    "odds_away":_float(row.get("B365A")),"over_odds":_float(row.get("B365>2.5")),
                    "under_odds":_float(row.get("B365<2.5")),
                })
    return sorted(rows, key=lambda x:(x["date"],x["league"],x["home"],x["away"]))


def _team_state():
    return {"points":deque(maxlen=8),"gf":deque(maxlen=8),"ga":deque(maxlen=8),
            "over":deque(maxlen=8),"btts":deque(maxlen=8)}


def _rate(values, default=0.5):
    return mean(values) if values else default


def _poisson_pmf(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _devig(odds: list[float], index: int) -> float | None:
    if len(odds) < 2 or any(x <= 1 for x in odds):
        return None
    raw = [1 / x for x in odds]
    total = sum(raw)
    return raw[index] / total if total else None


def _probabilities(h, a):
    hw, aw = min(8,len(h["gf"]))/8, min(8,len(a["gf"]))/8
    h_attack = 1.25*(1-hw) + _rate(h["gf"],1.25)*hw
    h_defense = 1.25*(1-hw) + _rate(h["ga"],1.25)*hw
    a_attack = 1.25*(1-aw) + _rate(a["gf"],1.25)*aw
    a_defense = 1.25*(1-aw) + _rate(a["ga"],1.25)*aw
    hl = max(.20,min(3.50,1.15*(h_attack/1.25)*(a_defense/1.25)))
    al = max(.20,min(3.00,.95*(a_attack/1.25)*(h_defense/1.25)))

    matrix={(hg,ag):_poisson_pmf(hg,hl)*_poisson_pmf(ag,al) for hg in range(9) for ag in range(9)}
    home_p=sum(p for (hg,ag),p in matrix.items() if hg>ag)
    draw_p=sum(p for (hg,ag),p in matrix.items() if hg==ag)
    away_p=sum(p for (hg,ag),p in matrix.items() if hg<ag)
    total=home_p+draw_p+away_p
    home_p,draw_p,away_p=[x/total for x in (home_p,draw_p,away_p)]

    btts_p=1-math.exp(-hl)-math.exp(-al)+math.exp(-(hl+al))
    over_p=1-sum(p for (hg,ag),p in matrix.items() if hg+ag<=2)

    form_edge=max(-1,min(1,(_rate(h["points"],1)-_rate(a["points"],1))/3))
    form_home=max(.05,min(.95,.50+.13*form_edge+.03))
    home_stat=max(.05,min(.95,.65*home_p+.35*form_home))
    home_pred=max(.05,min(.95,.75*home_p+.25*form_home))
    return {
        "home_win":(home_stat,.45*home_stat+.35*home_pred+.20*.50),
        "draw":(draw_p,draw_p),"away_win":(away_p,away_p),
        "btts_yes":(btts_p,btts_p),"over_2_5":(over_p,over_p),
    }


def run():
    history=load_history()
    states=defaultdict(_team_state)
    markets=("home_win","draw","away_win","btts_yes","over_2_5")
    points={m:{"model":[],"market_baseline":[]} for m in markets}
    tested=0
    odds_coverage={m:0 for m in markets}

    for row in history:
        h,a=states[row["home"]],states[row["away"]]
        if len(h["points"])>=3 and len(a["points"])>=3:
            probs=_probabilities(h,a)
            actuals={"home_win":int(row["hg"]>row["ag"]),"draw":int(row["hg"]==row["ag"]),
                     "away_win":int(row["hg"]<row["ag"]),"btts_yes":int(row["hg"]>0 and row["ag"]>0),
                     "over_2_5":int(row["hg"]+row["ag"]>=3)}
            odds={"home_win":row["odds"],"draw":row["odds_draw"],"away_win":row["odds_away"],
                  "over_2_5":row["over_odds"]}
            for market,actual in actuals.items():
                model_p,prod_p=probs[market]
                # BTTS has no proxy odds: do not attach O/U odds to it.
                model_odds=odds.get(market) if market != "btts_yes" else None
                points[market]["model"].append(CalibrationPoint(prod_p,actual,model_odds))

                if market in ("home_win","draw","away_win"):
                    trio=[row["odds"],row["odds_draw"],row["odds_away"]]
                    idx={"home_win":0,"draw":1,"away_win":2}[market]
                    baseline=_devig(trio,idx)
                elif market=="over_2_5":
                    baseline=_devig([row["over_odds"],row["under_odds"]],0)
                else:
                    baseline=None

                if baseline is not None:
                    points[market]["market_baseline"].append(
                        CalibrationPoint(baseline,actual,model_odds)
                    )
                    odds_coverage[market]+=1
            tested+=1

        h["points"].append(3 if row["hg"]>row["ag"] else 1 if row["hg"]==row["ag"] else 0)
        a["points"].append(3 if row["ag"]>row["hg"] else 1 if row["hg"]==row["ag"] else 0)
        h["gf"].append(row["hg"]); h["ga"].append(row["ag"])
        a["gf"].append(row["ag"]); a["ga"].append(row["hg"])
        total=row["hg"]+row["ag"]; over=int(total>=3); btts=int(row["hg"]>0 and row["ag"]>0)
        h["over"].append(over); a["over"].append(over); h["btts"].append(btts); a["btts"].append(btts)

    result={"generated_at":datetime.utcnow().isoformat()+"Z","seasons":list(SEASONS),
            "leagues":list(LEAGUES.values()),"tested_fixtures":tested,"odds_coverage":odds_coverage,
            "leakage_control":"walk-forward; current result enters state only after prediction",
            "markets":{m:{v:summarize(rows) for v,rows in variants.items()} for m,variants in points.items()}}
    out=Path("reports"); out.mkdir(exist_ok=True)
    (out/"historical_calibration_backtest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=="__main__":
    run()
