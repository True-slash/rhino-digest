"""
Rhino Daily News Digest Bot
============================
Fetches mobility/ride-hailing news from RSS feeds,
filters & summarizes with LLM, delivers via Telegram.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from fetcher import fetch_all_feeds
from deduplicator import Deduplicator
from filter import KeywordFilter
from summarizer import LLMSummarizer
from formatter import format_digest
from sender import TelegramSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    """Load settings from environment variables with sensible defaults."""
    return {
        "telegram_token": os.environ["TELEGRAM_BOT_TOKEN"],
        "telegram_chat_ids": os.environ["TELEGRAM_CHAT_IDS"].split(","),
        "llm_provider": os.getenv("LLM_PROVIDER", "groq"),        # groq | anthropic | gemini
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "max_articles_in_digest": int(os.getenv("MAX_ARTICLES", "15")),
        "min_relevance_score": int(os.getenv("MIN_RELEVANCE", "5")),
        "state_file": os.getenv("STATE_FILE", "data/seen_articles.json"),
    }


async def run():
    cfg = load_config()
    log.info("🦏 Rhino News Digest — starting")

    # 1. Fetch
    log.info("📡 Fetching RSS feeds...")
    articles = await fetch_all_feeds()
    log.info(f"   Fetched {len(articles)} raw articles")

    if not articles:
        log.warning("No articles fetched. Exiting.")
        return

    # 2. Deduplicate
    dedup = Deduplicator(cfg["state_file"])
    articles = dedup.filter_new(articles)
    log.info(f"   {len(articles)} after deduplication")

    if not articles:
        log.info("No new articles. Exiting.")
        return

    # 3. Keyword pre-filter (free, fast — removes obvious noise)
    kw_filter = KeywordFilter()
    articles = kw_filter.filter(articles)
    # Sort by keyword score so best articles go to LLM first
    articles.sort(key=lambda a: a.get("keyword_score", 0), reverse=True)
    log.info(f"   {len(articles)} after keyword pre-filter")

    # 4. LLM relevance scoring & summarization
    if cfg["llm_api_key"]:
        summarizer = LLMSummarizer(
            provider=cfg["llm_provider"],
            api_key=cfg["llm_api_key"],
            model=cfg["llm_model"],
        )
        articles = await summarizer.score_and_summarize(
            articles,
            min_score=cfg["min_relevance_score"],
            max_articles=cfg["max_articles_in_digest"],
        )
        log.info(f"   {len(articles)} after LLM scoring (≥{cfg['min_relevance_score']})")
    else:
        log.warning("No LLM_API_KEY set — using keyword scores only")
        articles.sort(key=lambda a: a.get("keyword_score", 0), reverse=True)
        articles = articles[: cfg["max_articles_in_digest"]]

    if not articles:
        log.info("No relevant articles today. Sending short notice.")
        articles = []

    # 5. Format
    digest_messages = format_digest(articles)

    # 6. Send
    sender = TelegramSender(cfg["telegram_token"])
    for chat_id in cfg["telegram_chat_ids"]:
        chat_id = chat_id.strip()
        for msg in digest_messages:
            await sender.send(chat_id, msg)
        log.info(f"   ✅ Sent to {chat_id}")

    # 7. Update state
    dedup.mark_seen(articles)
    dedup.save()
    log.info("🦏 Done!")


if __name__ == "__main__":
    asyncio.run(run())
