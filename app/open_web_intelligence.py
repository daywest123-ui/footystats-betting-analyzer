"""Public-web football intelligence without paid data APIs.

Uses public RSS feeds/search feeds and direct public pages where available.
It deliberately avoids authenticated APIs and does not bypass anti-bot controls.
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Iterable

import requests

USER_AGENT = "Mozilla/5.0 (compatible; FootballWebIntel/1.0; +https://github.com/daywest123-ui/footystats-betting-analyzer)"
TIMEOUT = 15

@dataclass
class WebMention:
    source: str
    title: str
    url: str
    published: str = ""
    text: str = ""
    language: str = ""
    sentiment: float = 0.0

POSITIVE = {"win", "wins", "winning", "favourite", "favorite", "strong", "confident", "likely", "back", "form", "beat", "beats", "good", "better", "galibiyet", "kazanır", "favori", "formda", "güçlü", "avantaj"}
NEGATIVE = {"loss", "lose", "losing", "injury", "injured", "suspended", "doubt", "doubtful", "poor", "weak", "bad", "defeat", "defeated", "mağlubiyet", "sakat", "cezalı", "şüpheli", "formsuz", "zayıf"}


def _clean(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _sentiment(text: str) -> float:
    words = set(re.findall(r"[\wğüşöçıİĞÜŞÖÇ]+", text.lower()))
    return (len(words & POSITIVE) - len(words & NEGATIVE)) / max(1, len(words & (POSITIVE | NEGATIVE)))


def google_news_rss(query: str, language: str = "en", country: str = "US", limit: int = 20) -> list[WebMention]:
    params = {"q": query, "hl": language, "gl": country, "ceid": f"{country}:{language}"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    result: list[WebMention] = []
    for item in root.findall("./channel/item")[:limit]:
        title = _clean(item.findtext("title", ""))
        link = item.findtext("link", "")
        description = _clean(item.findtext("description", ""))
        published = item.findtext("pubDate", "")
        result.append(WebMention("Google News RSS", title, link, published, description, language, _sentiment(title + " " + description)))
    return result


def collect_match_mentions(home: str, away: str, limit_per_query: int = 15) -> list[WebMention]:
    queries = [
        f'"{home}" "{away}" football',
        f'"{home}" "{away}" prediction',
        f'"{home}" "{away}" injuries lineup',
    ]
    # Turkish and international searches are intentionally separate.
    for lang, country in (("tr", "TR"), ("en", "US"), ("en", "GB")):
        queries.append(f'"{home}" "{away}" maç tahmin' if lang == "tr" else f'"{home}" "{away}" match prediction')

    mentions: list[WebMention] = []
    seen: set[str] = set()
    for i, query in enumerate(queries):
        lang, country = (("tr", "TR") if i == 3 else ("en", "US"))
        try:
            for m in google_news_rss(query, lang, country, limit_per_query):
                key = m.url or m.title
                if key not in seen:
                    seen.add(key)
                    mentions.append(m)
        except (requests.RequestException, ET.ParseError):
            continue
        time.sleep(0.25)
    return mentions


def aggregate(mentions: Iterable[WebMention]) -> dict:
    rows = list(mentions)
    if not rows:
        return {"mentions": 0, "web_score": 0.0, "confidence": 0.0, "sources": [], "risk_flags": ["web_data_unavailable"]}
    score = sum(m.sentiment for m in rows) / len(rows)
    injuries = sum(1 for m in rows if any(x in (m.title + " " + m.text).lower() for x in ("injury", "injured", "sakat", "cezalı", "suspended")))
    return {
        "mentions": len(rows),
        "web_score": round(score, 4),
        "confidence": round(min(1.0, 0.25 + 0.05 * min(len(rows), 15)), 4),
        "sources": sorted({m.source for m in rows}),
        "risk_flags": (["multiple_injury_or_suspension_mentions"] if injuries >= 2 else []),
        "items": [asdict(m) for m in rows],
    }


def analyze_match(home: str, away: str) -> dict:
    mentions = collect_match_mentions(home, away)
    result = aggregate(mentions)
    result.update({"home": home, "away": away})
    return result

if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("home")
    parser.add_argument("away")
    args = parser.parse_args()
    print(json.dumps(analyze_match(args.home, args.away), ensure_ascii=False, indent=2))
