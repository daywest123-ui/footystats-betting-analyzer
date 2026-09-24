"""Optional open-source integration status checks."""
from __future__ import annotations
import importlib.util
import shutil
from dataclasses import dataclass

@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    installed: bool
    command: str | None = None
    note: str = ""

def status() -> list[IntegrationStatus]:
    return [
        IntegrationStatus("FootStats",
            importlib.util.find_spec("footystats") is not None,
            note="Optional package; FootyStats account/data access may still be required."),
        IntegrationStatus("OddsHarvester",
            importlib.util.find_spec("oddsharvester") is not None,
            command=shutil.which("oddsharvester"),
            note="Optional MIT package; uses OddsPortal browser scraping."),
        IntegrationStatus("Selenium",
            importlib.util.find_spec("selenium") is not None,
            command=shutil.which("python"),
            note="Used by browser-based collectors."),
    ]

def as_dict() -> list[dict]:
    return [s.__dict__ for s in status()]
