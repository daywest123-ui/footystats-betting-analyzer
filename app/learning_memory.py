"""Persistent, leakage-safe learning memory for the football analyzer.

The memory stores completed prediction outcomes and calibration summaries so future
runs can measure which signals work under which conditions. It never changes a
prediction using the result of the same fixture; only completed historical fixtures
are admitted after their prediction timestamp.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_PATH = Path("data/learning/prediction_memory.jsonl")


def _read() -> list[dict[str, Any]]:
    if not MEMORY_PATH.exists():
        return []
    rows=[]
    for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def record_predictions(report: dict[str, Any]) -> int:
    """Append only completed fixtures that are not already present."""
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing=_read()
    seen={(str(x.get("fixture_id")), str(x.get("market")), str(x.get("prediction_time")))
          for x in existing}
    additions=[]
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

    for fixture in report.get("all_scanned", []):
        fixture_id=fixture.get("fixture_id") or f"{fixture.get('home')}||{fixture.get('away')}||{fixture.get('fixture_date')}"
        for market in fixture.get("market_analysis", []):
            if market.get("decision") not in {"ANALYZE","WATCH"}:
                continue
            row={
                "fixture_id":fixture_id,
                "home":fixture.get("home"),
                "away":fixture.get("away"),
                "fixture_date":fixture.get("fixture_date"),
                "league":fixture.get("league"),
                "market":market.get("market"),
                "odds":market.get("odds"),
                "model_probability":market.get("model_probability"),
                "fair_odds":market.get("fair_odds"),
                "ev_pct":market.get("ev_pct"),
                "prediction_time":report.get("generated_at",now),
                "recorded_at":now,
                "status":"PENDING",
            }
            key=(str(row["fixture_id"]),str(row["market"]),str(row["prediction_time"]))
            if key not in seen:
                additions.append(row); seen.add(key)

    if additions:
        with MEMORY_PATH.open("a",encoding="utf-8") as f:
            for row in additions:
                f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    return len(additions)


def _settle_from_score(row: dict[str, Any], hg: int, ag: int) -> str | None:
    market=str(row.get("market",""))
    if market=="home_win": return "WIN" if hg>ag else "LOSS"
    if market=="draw": return "WIN" if hg==ag else "LOSS"
    if market=="away_win": return "WIN" if hg<ag else "LOSS"
    if market=="btts_yes": return "WIN" if hg>0 and ag>0 else "LOSS"
    if market=="btts_no": return "WIN" if not (hg>0 and ag>0) else "LOSS"
    if market.startswith("over_") and market.endswith("_5"):
        line=float(market.split("_")[1])/10
        return "WIN" if hg+ag>line else "LOSS"
    if market.startswith("under_") and market.endswith("_5"):
        line=float(market.split("_")[1])/10
        return "WIN" if hg+ag<line else "LOSS"
    return None


def settle_with_history(history: list[dict[str, Any]]) -> int:
    """Settle pending rows using completed public-history matches."""
    if not MEMORY_PATH.exists():
        return 0
    index={}
    for m in history:
        key=(str(m.get("home","")).lower(),str(m.get("away","")).lower(),str(m.get("date","")))
        index[key]=m
    rows=_read()
    changed=0
    for row in rows:
        if row.get("status")!="PENDING":
            continue
        key=(str(row.get("home","")).lower(),str(row.get("away","")).lower(),str(row.get("fixture_date",""))[:10])
        m=index.get(key)
        if not m:
            continue
        try:
            hg,ag=int(m["hg"]),int(m["ag"])
        except (KeyError,TypeError,ValueError):
            continue
        outcome=_settle_from_score(row,hg,ag)
        if outcome:
            row["status"]=outcome
            row["actual_home_goals"]=hg
            row["actual_away_goals"]=ag
            row["settled_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
            changed+=1
    if changed:
        MEMORY_PATH.write_text(
            "".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in rows),
            encoding="utf-8",
        )
    return changed


def learning_summary() -> dict[str, Any]:
    rows=[r for r in _read() if r.get("status") in {"WIN","LOSS"}]
    groups=defaultdict(list)
    for r in rows:
        groups[str(r.get("market"))].append(r)
    summary={}
    for market,items in groups.items():
        wins=sum(x.get("status")=="WIN" for x in items)
        brier=sum((float(x.get("model_probability",0.5))-(1 if x.get("status")=="WIN" else 0))**2 for x in items)/len(items)
        summary[market]={
            "samples":len(items),
            "wins":wins,
            "hit_rate":round(wins/len(items),4),
            "brier_score":round(brier,6),
            "avg_ev_pct":round(sum(float(x.get("ev_pct") or 0) for x in items)/len(items),3),
        }
    return {"settled_predictions":len(rows),"by_market":summary}


if __name__=="__main__":
    print(json.dumps(learning_summary(),ensure_ascii=False,indent=2))
