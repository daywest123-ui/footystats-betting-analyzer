"""Load a locally collected FootyStats snapshot into the analyzer pipeline."""
from __future__ import annotations
import json
from pathlib import Path

def load_snapshot(path: str = "data/footystats_snapshot.json") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            "FootyStats snapshot bulunamadı. Önce footystats_local_connector.py çalıştırın."
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "source": data.get("source"),
        "collected_at_utc": data.get("collected_at_utc"),
        "url": data.get("url"),
        "title": data.get("title"),
        "raw_text": data.get("body_text", ""),
        "tables": data.get("tables", []),
    }
