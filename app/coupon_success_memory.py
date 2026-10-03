"""Memory of user-provided historical winning coupon selections."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

MEMORY_PATH=Path("data/learning/successful_coupon_memory.jsonl")

SEED=[
{"date":"2026-09-26","market":"home_win","odds":2.49,"won":True},
{"date":"2026-09-26","market":"home_win","odds":1.31,"won":True},
{"date":"2026-09-26","market":"home_win","odds":2.21,"won":True},
{"date":"2026-09-26","market":"away_win","odds":1.93,"won":True},
{"date":"2026-09-28","market":"btts_yes","odds":1.24,"won":True},
{"date":"2026-09-28","market":"under_2_5","odds":1.48,"won":True},
{"date":"2026-09-28","market":"btts_yes","odds":1.39,"won":True},
{"date":"2026-09-28","market":"btts_no","odds":1.32,"won":True},
{"date":"2026-09-28","market":"over_2_5","odds":1.48,"won":True},
{"date":"2026-09-28","market":"under_2_5","odds":1.60,"won":True},
{"date":"2026-09-28","market":"under_2_5","odds":1.51,"won":True},
]

def seed_if_missing():
    MEMORY_PATH.parent.mkdir(parents=True,exist_ok=True)
    if not MEMORY_PATH.exists():
        MEMORY_PATH.write_text("".join(json.dumps(x,ensure_ascii=False,separators=(",",":"))+"\n" for x in SEED),encoding="utf-8")

def _rows():
    seed_if_missing()
    out=[]
    for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict) and x.get("market"): out.append(x)
        except json.JSONDecodeError:
            pass
    return out

def _bucket(odds):
    if odds is None: return None
    x=float(odds)
    if x<1.40:return "1.20-1.39"
    if x<1.60:return "1.40-1.59"
    if x<2.00:return "1.60-1.99"
    if x<2.50:return "2.00-2.49"
    return "2.50+"

def market_stats():
    groups={}
    for x in _rows(): groups.setdefault(str(x["market"]),[]).append(x)
    out={}
    for market,items in groups.items():
        wins=sum(bool(x.get("won")) for x in items)
        out[market]={"samples":len(items),"wins":wins,"shrunk_rate":(wins+2)/(len(items)+4)}
    return out

def success_bonus(market,odds=None):
    s=market_stats().get(str(market))
    if not s:return 0.0
    bonus=3.0*max(0.0,float(s["shrunk_rate"])-0.5)
    if odds is not None:
        bucket=_bucket(odds)
        total=sum(1 for x in _rows() if x.get("market")==market)
        same=sum(1 for x in _rows() if x.get("market")==market and _bucket(x.get("odds"))==bucket)
        if total:
            bonus+=0.75*max(0.0,(same+1)/(total+2)-0.5)
    return round(min(bonus,3.75),4)
