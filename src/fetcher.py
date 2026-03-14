"""
Parallel async RSS feed fetcher.
Fetches Google News RSS (EN + PT-BR) and direct outlet feeds.
"""

import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx

log = logging.getLogger(__name__)

# ── Google News RSS feeds ────────────────────────────────────────────
# Customize queries here. Google News supports OR, AND, site:, after:
GOOGLE_NEWS_FEEDS = {
    # English — global ride-hailing & mobility
    "Ride-hailing EN": (
        "https://news.google.com/rss/search?"
        "q=ride-hailing+OR+ride-sharing+OR+Uber+OR+Lyft+OR+Bolt+OR+Grab+OR+DiDi+OR+inDrive+OR+Yango+OR+99+OR+Yandex+Go+OR+Cabify+OR+Freenow+OR+Gett+OR+Ola+OR+Waymo+OR+Blacklane+OR+Wheely+OR+Moove+OR+Kovi+OR+Jet+OR+Gettransfer+OR+Rapido+OR+Revel"
        "+when:24h&hl=en-US&gl=US&ceid=US:en"
    ),
    "Mobility tech EN": (
        "https://news.google.com/rss/search?"
        "q=robotaxi+OR+autonomous+vehicle+OR+mobility+OR+mobility-as-a-service+OR+micro-mobility"
        "+when:24h&hl=en-US&gl=US&ceid=US:en"
    ),
    "EV fleet EN": (
        "https://news.google.com/rss/search?"
        "q=electric+vehicle+fleet+OR+EV+ride-hailing+OR+EV+taxi"
        "+when:24h&hl=en-US&gl=US&ceid=US:en"
    ),

    # Portuguese — Brazil mobility, startups, fintech
    "Mobilidade BR": (
        "https://news.google.com/rss/search?"
        "q=Uber+OR+99+OR+inDrive+OR+mobilidade+OR+mobilidade+urbana+OR+transporte+por+aplicativo"
        "+when:24h&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),
    "Startups BR": (
        "https://news.google.com/rss/search?"
        "q=startup+Brasil+OR+venture+capital+Brasil+OR+VC+Brasil"
        "+when:24h&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),
    "Security BR": (
    "https://news.google.com/rss/search?"
    "q=segurança+veicular+OR+carro+blindado+OR+armored+vehicle"
    "+when:24h&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),
    "Regulação BR": (
        "https://news.google.com/rss/search?"
        "q=regulação+transporte+aplicativo+OR+táxi+regulamentação+Brasil"
        "+when:24h&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),
}

# ── Direct RSS feeds from key outlets ────────────────────────────────
DIRECT_FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "Rest of World": "https://restofworld.org/feed/latest",
    "Tecnoblog": "https://tecnoblog.net/feed/",
    "Exame": "https://exame.com/feed/",
    "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",
    "Bloomberg Tech": "https://feeds.bloomberg.com/technology/news.rss",
    "The Verge": "https://www.theverge.com/rss/index.xml",
}

# Maximum age of articles to consider (hours)
MAX_AGE_HOURS = 48


@dataclass
class Article:
    title: str
    url: str
    source: str
    published: Optional[str] = None
    snippet: str = ""
    language: str = "en"
    keyword_score: int = 0
    relevance_score: int = 0
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_rss(xml_text: str, source_name: str, language: str = "en") -> list[Article]:
    """Parse RSS XML into Article objects."""
    articles = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as e:
        log.warning(f"XML parse error for {source_name}: {e}")
        return []

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        desc_el = item.find("description")

        if title_el is None or link_el is None:
            continue

        title = title_el.text or ""
        url = link_el.text or ""
        published = pub_el.text if pub_el is not None else None
        snippet = desc_el.text or "" if desc_el is not None else ""

        # Strip HTML tags from snippet
        import re
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()[:500]

        articles.append(Article(
            title=title.strip(),
            url=url.strip(),
            source=source_name,
            published=published,
            snippet=snippet,
            language=language,
        ))

    return articles


async def _fetch_feed(
    client: httpx.AsyncClient, name: str, url: str, language: str = "en"
) -> list[Article]:
    """Fetch a single RSS feed."""
    try:
        resp = await client.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return _parse_rss(resp.text, name, language)
    except Exception as e:
        log.warning(f"Failed to fetch {name}: {e}")
        return []


async def fetch_all_feeds() -> list[dict]:
    """Fetch all configured feeds in parallel. Returns list of article dicts."""
    tasks = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "RhinoNewsBot/1.0"},
        http2=True,
    ) as client:

        # Google News feeds
        for name, url in GOOGLE_NEWS_FEEDS.items():
            lang = "pt" if "BR" in name else "en"
            tasks.append(_fetch_feed(client, name, url, lang))

        # Direct feeds
        for name, url in DIRECT_FEEDS.items():
            lang = "pt" if name in ("Tecnoblog", "Exame") else "en"
            tasks.append(_fetch_feed(client, name, url, lang))

        results = await asyncio.gather(*tasks)

    # Flatten, filter by age, and convert to dicts
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    all_articles = []
    skipped_old = 0
    for batch in results:
        for article in batch:
            # Filter by publish date if available
            if article.published:
                try:
                    from email.utils import parsedate_to_datetime
                    pub_dt = parsedate_to_datetime(article.published)
                    if pub_dt < cutoff:
                        skipped_old += 1
                        continue
                except Exception:
                    pass  # If date parsing fails, include the article
            all_articles.append(article.to_dict())

    if skipped_old:
        log.info(f"Skipped {skipped_old} articles older than {MAX_AGE_HOURS}h")
    log.info(f"Fetched {len(all_articles)} articles from {len(tasks)} feeds")
    return all_articles
