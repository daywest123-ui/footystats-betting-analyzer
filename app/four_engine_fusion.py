"""Four-engine probability fusion for football coupon markets."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import math

def _clamp(x: float, lo=.01, hi=.99) -> float:
    return max(lo, min(hi, float(x)))

def _mean(values, default=.5):
    vals=[float(v) for v in values if v is not None]
    return sum(vals)/len(vals) if vals else default

def _poisson_tail(lam: float, line: float) -> float:
    threshold=math.floor(float(line))+1
    return _clamp(1.0-sum(math.exp(-lam)*(lam**k)/math.factorial(k) for k in range(threshold)))

def _corner_line(market:str)->float:
    return float(market.split("_")[1])/10.0

@dataclass(frozen=True)
class EngineVote:
    name:str; probability:float; weight:float; available:bool; reason:str

def _dc_key(market):
    return {"home_win":"home_win","draw":"draw","away_win":"away_win","btts_yes":"btts_yes",
            "btts_no":"btts_no","over_2_5":"over_2_5","under_2_5":"under_2_5"}.get(market)


def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _xg_probability(market: str, fs: dict[str, Any]) -> EngineVote:
    """Match-specific xG engine; only active when both xG inputs exist."""
    try:
        lh = float(fs.get("home_xg"))
        la = float(fs.get("away_xg"))
    except (TypeError, ValueError):
        return EngineVote("XG_CONSENSUS", .5, 0, False, "match xG unavailable")
    if lh <= 0 or la <= 0:
        return EngineVote("XG_CONSENSUS", .5, 0, False, "invalid xG")
    max_goals = 10
    matrix = {(h, a): _poisson_pmf(lh, h) * _poisson_pmf(la, a)
              for h in range(max_goals + 1) for a in range(max_goals + 1)}
    total = sum(matrix.values())
    if total:
        matrix = {k: v / total for k, v in matrix.items()}
    if market == "home_win":
        p = sum(v for (h, a), v in matrix.items() if h > a)
    elif market == "draw":
        p = sum(v for (h, a), v in matrix.items() if h == a)
    elif market == "away_win":
        p = sum(v for (h, a), v in matrix.items() if h < a)
    elif market == "btts_yes":
        p = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    elif market == "btts_no":
        p = 1 - (1 - math.exp(-lh)) * (1 - math.exp(-la))
    elif market.startswith(("over_", "under_")) and not market.endswith("_corners"):
        line = float(market.split("_")[1]) / 10
        over = 1 - sum(math.exp(-(lh + la)) * ((lh + la) ** k) / math.factorial(k)
                       for k in range(math.floor(line) + 1))
        p = over if market.startswith("over_") else 1 - over
    else:
        return EngineVote("XG_CONSENSUS", .5, 0, False, "xG engine does not support market")
    return EngineVote("XG_CONSENSUS", _clamp(p), .18, True, f"match xG {lh:.2f}-{la:.2f}")

def _footystats_probability(market,fs,hf,af):
    fs,hf,af=fs or {},hf or {},af or {}
    exact={"btts_yes":fs.get("btts_rate"),"over_0_5":fs.get("over_05_rate"),
           "over_1_5":fs.get("over_15_rate"),"over_2_5":fs.get("over_25_rate"),
           "over_3_5":fs.get("over_35_rate"),"btts_1h_yes":fs.get("btts_1h_rate"),
           "btts_2h_yes":fs.get("btts_2h_rate")}
    if market in exact and exact[market] is not None:
        return EngineVote("FOOTYSTATS",_clamp(exact[market]),.30,True,"exact FootyStats rate")
    if market=="home_win":
        h=float(hf.get("points_per_game",1));a=float(af.get("points_per_game",1))
        gd=float(hf.get("goal_diff_per_game",0))-float(af.get("goal_diff_per_game",0))
        return EngineVote("FOOTYSTATS",_clamp(.50+(h-a)/20+gd/18+.03),.30,True,"form strength")
    if market=="draw":
        return EngineVote("FOOTYSTATS",_clamp(.27-.04*abs(float(hf.get("points_per_game",1))-float(af.get("points_per_game",1)))),.20,True,"form parity")
    if market=="away_win":
        h=float(hf.get("points_per_game",1));a=float(af.get("points_per_game",1))
        gd=float(af.get("goal_diff_per_game",0))-float(hf.get("goal_diff_per_game",0))
        return EngineVote("FOOTYSTATS",_clamp(.50+(a-h)/20+gd/18),.25,True,"away form strength")
    if market=="btts_no" and exact.get("btts_yes") is not None:
        return EngineVote("FOOTYSTATS",_clamp(1-float(exact["btts_yes"])),.30,True,"BTTS complement")
    if market.startswith(("under_0_5","under_1_5","under_2_5","under_3_5")):
        base=market.replace("under_","over_"); field={"over_0_5":"over_05_rate","over_1_5":"over_15_rate","over_2_5":"over_25_rate","over_3_5":"over_35_rate"}.get(base)
        if field and fs.get(field) is not None:
            return EngineVote("FOOTYSTATS",_clamp(1-float(fs[field])),.30,True,"goal-line complement")
    if market.startswith("over_") and market.endswith("_corners") and fs.get("corners_avg") is not None:
        return EngineVote("FOOTYSTATS",_poisson_tail(float(fs["corners_avg"]),_corner_line(market)),.25,True,"corners-average Poisson")
    return EngineVote("FOOTYSTATS",.5,0,False,"required FootyStats feature unavailable")

def _ensemble_probability(market,hf,af,dc,fs):
    dc,fs=dc or {},fs or {}; key=_dc_key(market)
    if key and key in dc:p=float(dc[key])
    elif market=="btts_no" and "btts_yes" in dc:p=1-float(dc["btts_yes"])
    elif market.startswith("over_") and market.endswith("_corners") and fs.get("corners_avg") is not None:
        p=_poisson_tail(float(fs["corners_avg"]),_corner_line(market))
    else:return EngineVote("ENSEMBLE",.5,0,False,"no compatible ensemble feature")
    if market in ("btts_yes","over_2_5","home_win","away_win","draw"):
        base=_footystats_probability(market,fs,hf,af);p=.70*p+.30*base.probability
    return EngineVote("ENSEMBLE",_clamp(p),.25,True,"model + form ensemble")

def _bayesian_probability(market,dc):
    dc=dc or {};key=_dc_key(market)
    if key and key in dc:return EngineVote("BAYES_DIXON_COLES",_clamp(dc[key]),.30,True,"Poisson/Elo/Dixon-Coles")
    if market=="btts_no" and "btts_yes" in dc:return EngineVote("BAYES_DIXON_COLES",_clamp(1-dc["btts_yes"]),.30,True,"Dixon-Coles complement")
    return EngineVote("BAYES_DIXON_COLES",.5,0,False,"market unavailable in score model")

def _football_stats_probability(market,hf,af,fs):
    hf,af,fs=hf or {},af or {},fs or {}
    if market=="home_win":
        edge=(float(hf.get("goals_for_per_game",1.25))-float(af.get("goals_against_per_game",1.25)))-(float(af.get("goals_for_per_game",1.25))-float(hf.get("goals_against_per_game",1.25)));p=.50+edge/8
    elif market=="away_win":
        edge=(float(af.get("goals_for_per_game",1.25))-float(hf.get("goals_against_per_game",1.25)))-(float(hf.get("goals_for_per_game",1.25))-float(af.get("goals_against_per_game",1.25)));p=.50+edge/8
    elif market=="draw":p=.27-.04*abs(float(hf.get("points_per_game",1))-float(af.get("points_per_game",1)))
    elif market=="btts_yes":p=_mean([hf.get("btts_rate"),af.get("btts_rate"),fs.get("btts_rate")])
    elif market.startswith("over_") and not market.endswith("_corners"):
        field={"over_0_5":"over_05_rate","over_1_5":"over_15_rate","over_2_5":"over_25_rate","over_3_5":"over_35_rate"}.get(market)
        if not field or fs.get(field) is None:return EngineVote("FOOTY_STATS",.5,0,False,"missing goal-line feature")
        p=fs[field]
    elif market.startswith("under_") and not market.endswith("_corners"):
        base=market.replace("under_","over_");field={"over_0_5":"over_05_rate","over_1_5":"over_15_rate","over_2_5":"over_25_rate","over_3_5":"over_35_rate"}.get(base)
        if not field or fs.get(field) is None:return EngineVote("FOOTY_STATS",.5,0,False,"missing goal-line feature")
        p=1-float(fs[field])
    elif market.endswith("_corners") and fs.get("corners_avg") is not None:
        p=_poisson_tail(float(fs["corners_avg"]),_corner_line(market))
    else:return EngineVote("FOOTY_STATS",.5,0,False,"unsupported market")
    return EngineVote("FOOTY_STATS",_clamp(p),.15,True,"feature-engineered football statistics")

def fuse_market(market,*,footystats,home_form,away_form,dixon_coles,web_probability=None,web_confidence=0):
    votes=[_footystats_probability(market,footystats,home_form,away_form),
           _ensemble_probability(market,home_form,away_form,dixon_coles,footystats),
           _bayesian_probability(market,dixon_coles),
           _football_stats_probability(market,home_form,away_form,footystats),
           _xg_probability(market,footystats)]
    if web_probability is not None and web_confidence>0:votes.append(EngineVote("WEB_INTELLIGENCE",_clamp(web_probability),min(.10,.10*web_confidence),True,"bounded web intelligence"))
    active=[v for v in votes if v.available and v.weight>0];total=sum(v.weight for v in active)
    p=sum(v.probability*v.weight for v in active)/total if total else .5
    dispersion=math.sqrt(_mean([(v.probability-p)**2 for v in active],0));agreement=sum(abs(v.probability-p)<=.08 for v in active)
    samples=min(int((home_form or {}).get("matches",0)),int((away_form or {}).get("matches",0)),8)
    quality=_clamp(.45+.10*len(active)+.05*samples-min(.25,dispersion),0,1)
    xg_h = footystats.get("home_xg") if footystats else None
    xg_a = footystats.get("away_xg") if footystats else None
    xg_diff = None
    try:
        if xg_h is not None and xg_a is not None:
            xg_diff = round(float(xg_h) - float(xg_a), 4)
    except (TypeError, ValueError):
        xg_diff = None
    return {"market":market,"probability":round(_clamp(p),6),"probability_pct":round(_clamp(p)*100,2),
            "engine_count":len(active),"agreement":agreement,"dispersion":round(dispersion,5),
            "data_quality":round(quality,4),"xg_home":xg_h,"xg_away":xg_a,"xg_diff":xg_diff,
            "votes":[{"engine":v.name,"probability_pct":round(v.probability*100,2),"weight":v.weight,"reason":v.reason} for v in votes if v.available]}
