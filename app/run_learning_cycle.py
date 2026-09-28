"""Execute one persistent learning cycle after the production analysis.

1) Settle older pending predictions against keyless Football-Data history.
2) Append the current analyzer's eligible/watch predictions.
3) Emit a compact learning summary for the next run/operator.
"""
from __future__ import annotations
import json
from pathlib import Path

from app.football_data_client import load_openfootball
from app.learning_memory import learning_summary, record_predictions, settle_with_history

def main():
    history=load_openfootball()
    settled=settle_with_history(history)
    report_path=Path("reports/latest_auto_analysis.json")
    added=0
    if report_path.exists():
        report=json.loads(report_path.read_text(encoding="utf-8"))
        added=record_predictions(report)
    summary=learning_summary()
    summary["cycle"]={"settled":settled,"new_predictions":added}
    out=Path("reports"); out.mkdir(exist_ok=True)
    (out/"learning_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
