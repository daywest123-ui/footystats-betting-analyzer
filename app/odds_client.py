"""Keyless odds reader.

Reads the downloadable football-data.co.uk CSV files through the open-data
layer. No API key, API endpoint, or bookmaker login is required.
"""
from __future__ import annotations
from football_data_client import fixture_odds

MARKET_MAP={
 "home_win":"home_win","draw":"draw","away_win":"away_win",
 "btts_yes":"btts_yes","btts_no":"btts_no",
 "over_2_5":"over_2_5","under_2_5":"under_2_5",
}

def get_fixture_odds(fixture_id):
    if not isinstance(fixture_id,str) or "||" not in fixture_id:
        raise ValueError("fixture_id must be home||away||YYYY-MM-DD")
    home,away,day=fixture_id.split("||",2)
    return {"markets":fixture_odds(home,away,day),"source":"football-data.co.uk CSV"}

def extract_markets(payload):
    return dict(payload.get("markets") or {})
