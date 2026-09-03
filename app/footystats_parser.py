"""Parse the FootyStats Match Filter snapshot collected from the user's local browser.

The source page is a text-oriented export, so parsing is deliberately conservative:
records are only emitted when a complete numeric row can be aligned with a known
match header. Unknown/misaligned rows are skipped rather than guessed.
"""
from __future__ import annotations
import re
from footystats_snapshot_loader import load_snapshot

MARKERS = ["KO Time", "AVG", "BTTS", "+1.5 GLS"]
HEADER_RE = re.compile(r"^\d+(?:st|nd|rd|th),\s+\d{2}:\d{2}$")
NUM_RE = re.compile(r"^(?:\d+(?:\.\d+)?%?|N/A)$")
LEAGUE_HINTS = {"Serie", "Liga", "Primera", "Division", "Copa", "Championship", "Campeonato", "Tercera", "Categoria"}

def _is_number(v): return bool(NUM_RE.match(v))

def parse_snapshot(path="data/footystats_snapshot.json"):
    raw = load_snapshot(path)["raw_text"]
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    try:
        start = next(i for i,x in enumerate(lines) if x == "KO Time" and lines[i+1:i+4] == ["AVG","BTTS","+1.5 GLS"])
    except (StopIteration, IndexError):
        return []

    data = lines[start+1:]
    matches=[]; i=0
    while i < len(data):
        if not HEADER_RE.match(data[i]):
            i += 1; continue
        ko=data[i]; i+=1
        # League names may contain multiple words; numeric block starts after home/away.
        # Match filter currently emits: KO, league, home, away, then numeric values.
        if i+2 >= len(data): break
        league=data[i]; home=data[i+1]; away=data[i+2]; i+=3
        nums=[]
        while i < len(data) and not HEADER_RE.match(data[i]):
            if _is_number(data[i]): nums.append(data[i])
            i+=1
        if len(nums) < 20: continue
        def val(n, pct=False):
            if n >= len(nums) or nums[n]=="N/A": return None
            x=nums[n].replace("%","")
            return float(x)/100 if pct else float(x)
        # Column positions are based on the visible Match Filter header order.
        matches.append({
            "source":"footystats",
            "kickoff":ko, "league":league, "home":home, "away":away,
            "avg_goals":val(2), "btts_rate":val(3,True),
            "over_15_rate":val(4,True), "over_25_rate":val(5,True),
            "corners_avg":val(6), "cards_avg":val(7),
            "over_05_rate":val(8,True), "over_35_rate":val(9,True),
            "home_xg":val(10), "away_xg":val(11),
            "btts_1h_rate":val(12,True), "btts_2h_rate":val(13,True),
            "odds":{"home_win":val(14),"draw":val(15),"away_win":val(16),
                    "btts_yes":val(17),"over_05":val(18),"over_15":val(19),
                    "over_25":val(20),"over_35":val(21),
                    "under_15":val(22),"under_25":val(23),"under_35":val(24),
                    "over_85_corners":val(26),"over_95_corners":val(27),
                    "over_105_corners":val(28)}
        })
    return matches
