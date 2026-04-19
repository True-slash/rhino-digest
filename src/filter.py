"""
Fast keyword-based pre-filter.
Eliminates obviously irrelevant articles BEFORE sending to LLM.
This saves API calls and money.
"""

import logging
import re

log = logging.getLogger(__name__)

# ── Keywords by category (weighted) ─────────────────────────────────
# Weight 3: Core business terms
HIGH_KEYWORDS = [
    "ride-hailing", "ride-sharing", "rideshare", "ride hailing", "taxi",
    "táxi por aplicativo", "transporte por aplicativo",
    "mobilidade urbana", "urban mobility",
    "armored vehicle", "blindado", "segurança veicular",
    "armored taxi", "táxi blindado", "uber", "lyft", "didi", "indrive", "99",
]

# Weight 2: Key companies & direct competitors
MEDIUM_KEYWORDS = [
    "grab", "bolt", "cabify", "freenow", "gett", "ola", "yandex go",
    "waymo", "robotaxi", "autonomous taxi",
    "yango", "blacklane", "wheely", "moove", "kovi", "jet", 
    "gettransfer", "rapido", "revel", "armis mobi", "bunker driver", 
    "vou de blindados rj", "localiza", "movida", "wammo", "turbi",
    "venture capital", "VC", "série a", "series a", "funding", "fundraising",
    "bitaksi", "marti", "careem", "gojek", "ousta", "sixt", "blusmart", "meru", "savaari", "jugnoo", "bluebird", "xanh", "limogreen", "blablacar", "vemo", "beat", "libres", "picap",
]

# Weight 1: Broader relevant topics
LOW_KEYWORDS = [
    "gig economy", "economia gig", "motorista de aplicativo",
    "driver earnings", "ganhos motorista",
    "electric vehicle", "veículo elétrico", "ev fleet",
    "micro-mobility", "micromobilidade",
    "last mile", "última milha",
    "regulação", "regulation", "antt", "denatran",
    "fintech", "pagamento digital", "digital payment",
    "são paulo", "rio de janeiro", "brasil", "brazil", "latin america",
    "américa latina", "latam", "turkey", "türkiye", "egypt", "argentina", "india", "indonesia", "mexico", "colombia",
]

# Negative keywords — articles matching these are likely noise
NEGATIVE_KEYWORDS = [
    "uber eats recipe", "lyft stock buy sell",
    "celebrity", "entertainment", "sports score",
    "horoscope", "weather forecast",
]

# Minimum score to pass pre-filter
MIN_KEYWORD_SCORE = 3


class KeywordFilter:
    def __init__(self, min_score: int = MIN_KEYWORD_SCORE):
        self.min_score = min_score

    def score(self, article: dict) -> int:
        """Score an article based on keyword matches. Returns 0-10."""
        text = (
            article.get("title", "") + " " + article.get("snippet", "")
        ).lower()

        # Check negative keywords first
        for neg in NEGATIVE_KEYWORDS:
            if neg in text:
                return 0

        score = 0
        for kw in HIGH_KEYWORDS:
            if kw in text:
                score += 3
        for kw in MEDIUM_KEYWORDS:
            if kw in text:
                score += 2
        for kw in LOW_KEYWORDS:
            if kw in text:
                score += 1

        return min(score, 10)

    def filter(self, articles: list[dict]) -> list[dict]:
        """Filter articles by keyword score. Adds keyword_score to each article."""
        passed = []
        for art in articles:
            score = self.score(art)
            art["keyword_score"] = score
            if score >= self.min_score:
                passed.append(art)

        log.info(
            f"Keyword filter: {len(passed)}/{len(articles)} passed "
            f"(min_score={self.min_score})"
        )
        return passed
