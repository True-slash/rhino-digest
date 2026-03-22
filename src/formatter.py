"""
Formats the filtered articles into Telegram HTML messages.
Splits into multiple messages if over 4096 chars.
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Category labels based on keywords in title/snippet
CATEGORIES = {
    "🚗 Ride-hailing": [
        "uber", "lyft", "didi", "grab", "bolt", "indrive", "99",
        "cabify", "ride-hailing", "ride-sharing", "rideshare",
        "táxi", "taxi app",
    ],
    "🤖 Autonomous & EVs": [
        "robotaxi", "autonomous", "self-driving", "waymo", "cruise",
        "electric vehicle", "ev fleet", "veículo elétrico", "autônomo",
    ],
    "🛡️ Safety & Security": [
        "armored", "blindado", "segurança", "safety", "security",
        "crime", "violence", "assalto",
    ],
    "📜 Regulation": [
        "regulation", "regulação", "regulamentação", "legislation",
        "law", "lei", "antt", "policy", "política",
    ],
    "💰 Funding & Finance": [
        "funding", "investimento", "venture capital", "series",
        "ipo", "valuation", "acquisition", "aquisição", "rodada",
    ],
    "🇧🇷 Brazil": [
        "brasil", "brazil", "são paulo", "rio de janeiro",
        "latam", "latin america", "américa latina",
    ],
}


def _categorize(article: dict) -> str:
    """Assign a category emoji based on article content."""
    text = (article.get("title", "") + " " + article.get("snippet", "")).lower()

    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                return category

    return "📰 Industry"


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _escape_url(url: str) -> str:
    """Escape quotes in URLs for safe use in href attributes."""
    return url.replace('"', "%22").replace("'", "%27")


def format_digest(articles: list[dict]) -> list[str]:
    """
    Format articles into one or more Telegram HTML messages.
    Groups by category. Returns list of message strings.
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    if not articles:
        return [
            f"📰 <b>Rhino Daily Digest — {today}</b>\n\n"
            "No relevant news today."
        ]

    # Group articles by category
    grouped: dict[str, list[dict]] = {}
    for art in articles:
        cat = _categorize(art)
        grouped.setdefault(cat, []).append(art)

    # Build message body
    header = (
        f"📰 <b>Rhino Daily Digest — {today}</b>\n"
        f"📊 {len(articles)} stories curated for you\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )

    body_parts = []
    article_num = 1

    for category, arts in grouped.items():
        section = f"\n{category}\n\n"
        for art in arts[:5]:
            title = _escape_html(art.get("title", "Untitled"))
            url = _escape_url(art.get("url", ""))
            summary = art.get("summary", "")
            source = _escape_html(art.get("source", ""))
            score = art.get("relevance_score", art.get("keyword_score", 0))

            line = f'{article_num}. <a href="{url}"><b>{title}</b></a>\n'
            if summary:
                line += f"<i>{_escape_html(summary)}</i>\n"
            line += f"<code>{source}</code> · relevance: {score}/10\n"

            section += line + "\n"
            article_num += 1

        body_parts.append(section)

    footer = ""

    # Split into messages under 4096 chars
    messages = []
    current = header

    for part in body_parts:
        if len(current) + len(part) + len(footer) > 4000:
            if current.strip():
                messages.append(current)
            current = ""
        current += part

    current += footer
    if current.strip():
        messages.append(current)

    # Safety: split any message still over 4096
    final = []
    for msg in messages:
        while len(msg) > 4096:
            cut = msg[:4000].rfind("\n")
            if cut == -1:
                cut = 4000
            final.append(msg[:cut])
            msg = msg[cut:]
        if msg.strip():
            final.append(msg)

    return final if final else [full_message[:4000]]
