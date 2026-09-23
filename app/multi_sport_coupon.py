"""Legacy compatibility entry point.

The project is now football-only and keyless. This module deliberately does not
call API-Sports or The Odds API. It delegates to the open-data football scanner.
"""
from __future__ import annotations
from auto_match_selector import main

if __name__ == "__main__":
    main()
