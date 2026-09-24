from app import odds_harvester_client as oh


def test_extract_odds_1x2_btts_and_totals():
    record = {
        "odds": [
            {"outcome": "1", "odds": 2.10},
            {"outcome": "X", "odds": 3.40},
            {"outcome": "2", "odds": 3.70},
            {"outcome": "Yes", "odds": 1.72},
            {"outcome": "No", "odds": 2.05},
            {"outcome": "Over 2.5", "odds": 1.91},
            {"outcome": "Under 2.5", "odds": 1.89},
        ]
    }
    got = oh._extract_odds(record)
    assert got["home_win"] == 2.10
    assert got["draw"] == 3.40
    assert got["away_win"] == 3.70
    assert got["btts_yes"] == 1.72
    assert got["btts_no"] == 2.05
    assert got["over_2_5"] == 1.91
    assert got["under_2_5"] == 1.89


def test_fixture_matching_uses_normalized_team_names(monkeypatch):
    oh._CACHE.clear()
    oh._CACHE["2026-09-24"] = [{
        "home_team": "Liverpool FC",
        "away_team": "Chelsea",
        "odds": [
            {"outcome": "1", "odds": 2.25},
            {"outcome": "X", "odds": 3.40},
            {"outcome": "2", "odds": 3.10},
        ],
    }]
    got = oh.fixture_odds("Liverpool", "Chelsea", "2026-09-24")
    assert got["home_win"] == 2.25
    assert got["draw"] == 3.40
    assert got["away_win"] == 3.10


def test_current_fixtures_are_read_from_cache():
    oh._CACHE.clear()
    oh._CACHE["2026-09-24"] = [{
        "home_team": "Team A",
        "away_team": "Team B",
        "kickoff": "2026-09-24T19:00",
        "league": "Test League",
    }]
    rows = oh.current_fixtures("2026-09-24")
    assert rows[0]["home"] == "Team A"
    assert rows[0]["away"] == "Team B"
    assert rows[0]["finished"] is False
