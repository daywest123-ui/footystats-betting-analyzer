"""Central configuration for Ultimate Betting Analyzer."""

MIN_ODDS = 1.55
IDEAL_ODDS_MIN = 1.60
IDEAL_ODDS_MAX = 2.20
MIN_CONFIDENCE = 0.55
MIN_VALUE_EDGE = 0.00
HIGH_ODDS_WARNING = 2.50

SUPPORTED_MARKETS = [
    "home_win", "draw", "away_win",
    "btts_yes", "btts_no",
    "over_1_5", "over_2_5", "under_2_5",
    "over_3_5", "under_3_5",
    "first_half_over_0_5", "first_half_over_1_5",
    "double_chance", "team_goals",
    "corners_over_8_5", "corners_over_9_5",
    "cards_over_3_5", "cards_over_4_5",
]
