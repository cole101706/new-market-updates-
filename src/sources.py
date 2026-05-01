"""All data sources for live alerts."""
import hashlib
import re
from datetime import datetime, timezone

import feedparser
import httpx

USER_AGENT = "Mozilla/5.0 (LiveAlerts/1.0)"

MARKET_FEEDS = [
    ("CNBC Markets", "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
    ("MarketWatch Bulletins", "https://feeds.marketwatch.com/marketwatch/bulletins"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
]

ECONOMIC_FEEDS = [
    ("Fed Press", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("Fed FOMC", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    ("BLS", "https://www.bls.gov/feed/news_release.rss"),
    ("Treasury", "https://home.treasury.gov/news/press-releases/feed"),
    ("BEA", "https://apps.bea.gov/rss/rss.xml"),
]

WORLD_FEEDS = [
    ("Reuters World", "https://www.reutersagency.com/feed/?best-topics=world"),
    ("AP Top", "https://feeds.apnews.com/rss/apf-topnews"),
    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Middle East", "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsfrontpage.aspx"),
]

POLITICS_FEEDS = [
    ("Reuters Politics", "https://www.reutersagency.com/feed/?best-topics=political-general"),
    ("AP Politics", "https://feeds.apnews.com/rss/apf-politics"),
    ("The Hill", "https://thehill.com/homenews/feed/"),
    ("Politico", "https://rss.politico.com/politics-news.xml"),
]

HORMUZ_KW = [
    "hormuz", "strait of hormuz", "persian gulf", "gulf of oman",
    "tanker", "oil tanker", "crude tanker", "vessel seized",
    "iran", "iranian", "irgc", "revolutionary guard",
    "houthi", "red sea",
]

TRUMP_RELEVANT_KW = [
    "econom", "stock", "market", "tariff", "trade",
    "fed", "powell", "interest rate", "inflation", "dollar",
    "iran", "hormuz", "tanker", "war", "strike",
    "oil", "gas", "energy", "opec",
    "china", "deal", "sanction",
]

TRUMP_NAME_KW = ["trump", "president trump", "white house", "potus"]


def hash_id(text):
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


async def fetch_rss(url, timeout=12):
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return feedparser.parse(r.content)
    except Exception:
        return None


def entry_age_hours(entry):
    parsed = (
        getattr(entry, "published_parsed", None)
        or getattr(entry, "updated_parsed", None)
    )
    if not parsed:
        return None
    pub = datetime(*parsed[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - pub).total_seconds() / 3600.0


def is_recent(entry, max_age_hours):
    age = entry_age_hours(entry)
    if age is None:
        return True
    return age <= max_age_hours


def clean_text(s, limit=200):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


async def fetch_market_news(config):
    items = []
    max_age = config.get("market_max_age_hours", 1.0)
    for name, url in MARKET_FEEDS:
        feed = await fetch_rss(url)
        if not feed:
            continue
        for entry in feed.entries[:10]:
            if not is_recent(entry, max_age):
                continue
            title = clean_text(entry.get("title", ""), 200)
            link = entry.get("link", "")
            if not title:
                continue
            items.append({
                "id": hash_id(link or title),
                "title": "📈 " + name,
                "message": title,
                "url": link,
                "priority": 3,
                "tags": ["chart_with_upwards_trend"],
            })
    return items


async def fetch_economic_news(config):
    items = []
    max_age = config.get("economic_max_age_hours", 6)
    for name, url in ECONOMIC_FEEDS:
        feed = await fetch_rss(url)
        if not feed:
            continue
        for entry in feed.entries[:8]:
            if not is_recent(entry, max_age):
                continue
            title = clean_text(entry.get("title", ""), 200)
            link = entry.get("link", "")
            if not title:
                continue
            items.append({
                "id": hash_id(link or title),
                "title": "🏛️ " + name,
                "message": title,
                "url": link,
                "priority": 5,
                "tags": ["bank"],
            })
    return items


async def fetch_trump_posts(config):
    items = []
    max_age = config.get("trump_max_age_hours", 1.5)

    feed = await fetch_rss("https://trumpstruth.org/feed")
    if feed:
        for entry in feed.entries[:20]:
            if not is_recent(entry, max_age):
                continue
            title = clean_text(entry.get("title", ""), 200)
            summary = clean_text(entry.get("summary", ""), 400)
            blob = (title + " " + summary).lower()
            if not any(kw in blob for kw in TRUMP_RELEVANT_KW):
                continue
            link = entry.get("link", "")
            display = summary if summary else title
            items.append({
                "id": hash_id(link or title or summary),
                "title": "🔴 Trump (Truth Social)",
                "message": display[:300],
                "url": link,
                "priority": 5,
                "tags": ["loudspeaker"],
            })

    for name, url in POLITICS_FEEDS:
        f = await fetch_rss(url)
        if not f:
            continue
        for entry in f.entries[:10]:
            if not is_recent(entry, max_age):
                continue
            title = clean_text(entry.get("title", ""), 200)
            summary = clean_text(entry.get("summary", ""), 200)
            blob = (title + " " + summary).lower()
            if not any(kw in blob for kw in TRUMP_NAME_KW):
                continue
            if not any(kw in blob for kw in TRUMP_RELEVANT_KW):
                continue
            link = entry.get("link", "")
            items.append({
                "id": hash_id(link or title),
                "title": "🔴 Trump • " + name,
                "message": title,
                "url": link,
                "priority": 4,
                "tags": ["loudspeaker"],
            })

    return items


async def fetch_hormuz_news(config):
    items = []
    max_age = config.get("hormuz_max_age_hours", 4)
    for name, url in WORLD_FEEDS:
        feed = await fetch_rss(url)
        if not feed:
            continue
        for entry in feed.entries[:20]:
            if not is_recent(entry, max_age):
                continue
            title = clean_text(entry.get("title", ""), 200)
            summary = clean_text(entry.get("summary", ""), 200)
            blob = (title + " " + summary).lower()
            if not any(kw in blob for kw in HORMUZ_KW):
                continue
            link = entry.get("link", "")
            items.append({
                "id": hash_id(link or title),
                "title": "⚓ " + name,
                "message": title,
                "url": link,
                "priority": 5,
                "tags": ["anchor", "warning"],
            })
    return items


async def fetch_maritime_data(config):
    items = []
    cfg = config.get("maritime", {})
    if not cfg.get("enabled"):
        return items

    provider = cfg.get("provider", "datalastic")
    api_key = cfg.get("api_key")
    if not api_key:
        return items

    if provider == "datalastic":
        url = (
            "https://api.datalastic.com/api/v0/vessel_inradius"
            "?api-key=" + api_key + "&lat=26.5&lon=56.25&radius=50"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
            vessels = data.get("data", {}).get("vessels", []) or []
            tankers = [v for v in vessels if "tanker" in (v.get("type") or "").lower()]
            count_id = hash_id("hormuz-count-" + datetime.utcnow().strftime("%Y%m%d-%H"))
            items.append({
                "id": count_id,
                "title": "⚓ Hormuz traffic (hourly)",
                "message": str(len(vessels)) + " vessels in area, " + str(len(tankers)) + " tankers",
                "url": "https://www.marinetraffic.com/en/ais/home/centerx:56.25/centery:26.5/zoom:9",
                "priority": 2,
                "tags": ["ship"],
            })
        except Exception:
            pass

    return items
