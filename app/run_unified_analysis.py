"""CLI entry point for the unified football analysis core."""
from __future__ import annotations
import argparse, json
from app.unified_betting_engine import analyze_match_bundle

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("home"); ap.add_argument("away")
    ap.add_argument("--odds-json",default=None)
    ap.add_argument("--recent-limit",type=int,default=30)
    args=ap.parse_args()
    odds=json.loads(args.odds_json) if args.odds_json else None
    print(json.dumps(analyze_match_bundle(args.home,args.away,odds=odds,recent_limit=args.recent_limit),
                     ensure_ascii=False,indent=2))

if __name__=="__main__": main()
