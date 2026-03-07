"""
Deduplication using URL matching + fuzzy title similarity.
State stored as JSON (works with GitHub Actions commit-back pattern).
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger(__name__)

# Articles older than this are pruned from state
RETENTION_DAYS = 30
# Fuzzy title match threshold (0.0–1.0)
TITLE_SIMILARITY_THRESHOLD = 0.82


class Deduplicator:
    def __init__(self, state_file: str = "data/seen_articles.json"):
        self.state_file = state_file
        self.seen: dict[str, str] = {}      # url -> iso_date
        self.seen_titles: dict[str, str] = {}  # normalized_title -> url
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
        """Remove entries older than RETENTION_DAYS."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        old_count = len(self.seen)
        self.seen = {url: dt for url, dt in self.seen.items() if dt >= cutoff}
        pruned = old_count - len(self.seen)
        if pruned:
            log.info(f"Pruned {pruned} old entries from state")

    @staticmethod
    def _normalize_title(title: str) -> str:
        return title.lower().strip()

    def _is_title_duplicate(self, title: str) -> bool:
        norm = self._normalize_title(title)
        for seen_title in self.seen_titles:
            if SequenceMatcher(None, norm, seen_title).ratio() >= TITLE_SIMILARITY_THRESHOLD:
                return True
        return False

    def filter_new(self, articles: list[dict]) -> list[dict]:
        """Return only articles not previously seen."""
        new = []
        for art in articles:
            url = art.get("url", "")
            title = art.get("title", "")

            if url in self.seen:
                continue
            if self._is_title_duplicate(title):
                continue

            new.append(art)
        return new

    def mark_seen(self, articles: list[dict]):
        """Add articles to seen set."""
        now = datetime.now(timezone.utc).isoformat()
        for art in articles:
            url = art.get("url", "")
            title = art.get("title", "")
            if url:
                self.seen[url] = now
            if title:
                self.seen_titles[self._normalize_title(title)] = url

    def save(self):
        """Persist state to JSON."""
        Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump({
                "urls": self.seen,
                "titles": self.seen_titles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)
        log.info(f"State saved: {len(self.seen)} URLs tracked")
