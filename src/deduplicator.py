"""
Deduplication using URL matching + fuzzy title similarity.
State stored as JSON (works with GitHub Actions commit-back pattern).
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger(__name__)

RETENTION_DAYS = 30
TITLE_SIMILARITY_THRESHOLD = 0.50


def _clean_title(title: str) -> str:
    """Normalize title for comparison: lowercase, remove source suffix, punctuation."""
    title = title.lower().strip()
    title = re.sub(r'\s*[-–—|]\s*[^-–—|]+$', '', title)
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


class Deduplicator:
    def __init__(self, state_file: str = "data/seen_articles.json"):
        self.state_file = state_file
        self.seen: dict[str, str] = {}
        self.seen_titles: dict[str, str] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                self.seen = data.get("urls", {})
                self.seen_titles = data.get("titles", {})
                self._prune()
                log.info(f"Loaded {len(self.seen)} seen articles from state")
            except (json.JSONDecodeError, KeyError) as e:
                log.warning(f"Corrupt state file, starting fresh: {e}")
                self.seen = {}
                self.seen_titles = {}
        else:
            log.info("No state file found — first run")

    def _prune(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        old_count = len(self.seen)
        self.seen = {url: dt for url, dt in self.seen.items() if dt >= cutoff}
        pruned = old_count - len(self.seen)
        if pruned:
            log.info(f"Pruned {pruned} old entries from state")

    def _is_title_similar(self, title: str, title_list: list[str]) -> bool:
        clean = _clean_title(title)
        if len(clean) < 10:
            return False
        for seen_t in title_list:
            if SequenceMatcher(None, clean, seen_t).ratio() >= TITLE_SIMILARITY_THRESHOLD:
                return True
        return False

    def filter_new(self, articles: list[dict]) -> list[dict]:
        """Return only articles not previously seen, and deduplicate within batch."""
        new = []
        batch_titles = []
        for art in articles:
            url = art.get("url", "")
            title = art.get("title", "")

            if url in self.seen:
                continue

            seen_titles_list = list(self.seen_titles.keys())
            if self._is_title_similar(title, seen_titles_list):
                continue

            if self._is_title_similar(title, batch_titles):
                continue

            batch_titles.append(_clean_title(title))
            new.append(art)
        return new

    def mark_seen(self, articles: list[dict]):
        now = datetime.now(timezone.utc).isoformat()
        for art in articles:
            url = art.get("url", "")
            title = art.get("title", "")
            if url:
                self.seen[url] = now
            if title:
                self.seen_titles[_clean_title(title)] = url

    def save(self):
        Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump({
                "urls": self.seen,
                "titles": self.seen_titles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)
        log.info(f"State saved: {len(self.seen)} URLs tracked")
