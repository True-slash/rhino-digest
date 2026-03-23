"""
LLM-powered relevance scoring, summarization, and daily brief generation.
Supports multiple providers: Groq (free), Anthropic, Google Gemini.
Batches articles to minimize API calls.
"""

import asyncio
import json
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BATCH_SIZE = 10  # Articles per LLM call

SYSTEM_PROMPT = """You are a news analyst for Rhino, an armored ride-hailing startup in Brazil. You want them to success and at the very least sell the company at the unicorn level.

Your job: evaluate each article's relevance and write a short summary for the founders' daily digest.

HIGH relevance (8-10):
- Ride-hailing industry news (Uber, Lyft, DiDi, 99, Bolt, Grab, inDrive, Cabify, etc.), especially in premium segment
- Urban mobility, MaaS (mobility-as-a-service)
- Vehicle safety, armored vehicles, safety in transportation
- Brazil and Turkey transportation regulation and policy
- Competitor launches, pricing changes, market expansion
- Gig economy labor laws and driver issues
- Brazil and Turkey startup funding rounds (especially mobility, logistics)

MEDIUM relevance (5-7):
- Autonomous vehicles, robotaxis
- EV adoption for fleets, charging infrastructure
- Fintech / payments in mobility context
- Urban planning, public transit changes in major Brazilian cities

LOW relevance (1-4):
- General tech news without mobility angle
- News about companies above but unrelated to mobility (e.g. Uber Eats recipes)
- Generic Brazil economic news without transport/startup angle

For each article respond with ONLY a JSON array. Each element:
{
  "id": <article index, starting from 0>,
  "relevance": <0-10>,
  "summary": "<1-2 sentence summary in the SAME language as the article title, or null if relevance < 5>"
}

Return ONLY valid JSON, no markdown fences, no explanation."""

DAILY_BRIEF_PROMPT = """You are a strategic analyst for Rhino, an armored ride-hailing startup in Brazil.

CONTEXT ABOUT RHINO:
- Premium armored vehicle ride-hailing service in Brazil 
- Key concerns: competition (Uber, 99, inDrive, etc., especially in premium segment), regulation, safety/security, EV adoption, Latam market dynamics

Below are today's top articles with their summaries.

Write a super concise summary in English using EXACTLY this structure:

Key Attention Items:
(1 sentence on what demands immediate attention today — competitor launches, regulatory changes, major deals. If nothing urgent, say so.)

Market Impact:
(1 sentence on how today's news affects the ride-hailing market and trends relevant to Rhino.)

Threats:
(1 sentence on competitive threats or risks from today's news.)

Opportunities:
(1 sentence on opportunities Rhino could leverage.)

Bottom Line:
(1 sentence executive summary.)

If nothing noteworthy today, keep each section to one short sentence. Don't pad with generic statements.

IMPORTANT: Do NOT use any Markdown formatting (no **, no *, no #, no ```) or CAPSLOCK in summaries. Use plain text only. The output is sent to Telegram in HTML mode.

ARTICLES:
{articles_text}

Write the brief:"""

# ── Provider configurations ──────────────────────────────────────────

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "auth_header": "Bearer",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-haiku-4-5-20251001",
        "auth_header": "x-api-key",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "default_model": "gemini-2.0-flash-lite",
        "auth_header": "key",
    },
}


class LLMSummarizer:
    def __init__(self, provider: str, api_key: str, model: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
        self.model = model or PROVIDERS[provider]["default_model"]

    async def _call_llm(self, prompt: str, system: str = SYSTEM_PROMPT) -> str:
        """Call the LLM and return the text response."""
        async with httpx.AsyncClient(timeout=60) as client:
            if self.provider == "groq":
                return await self._call_openai_compatible(client, prompt, system)
            elif self.provider == "anthropic":
                return await self._call_anthropic(client, prompt, system)
            elif self.provider == "gemini":
                return await self._call_gemini(client, prompt, system)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")

    async def _call_openai_compatible(self, client: httpx.AsyncClient, prompt: str, system: str) -> str:
        cfg = PROVIDERS[self.provider]
        resp = await client.post(
            cfg["base_url"],
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 3000,
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, client: httpx.AsyncClient, prompt: str, system: str) -> str:
        resp = await client.post(
            PROVIDERS["anthropic"]["base_url"],
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 3000,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    async def _call_gemini(self, client: httpx.AsyncClient, prompt: str, system: str) -> str:
        url = PROVIDERS["gemini"]["base_url"].format(model=self.model)
        resp = await client.post(
            url,
            params={"key": self.api_key},
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 3000},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _build_batch_prompt(self, articles: list[dict]) -> str:
        """Format a batch of articles for the LLM."""
        lines = []
        for i, art in enumerate(articles):
            lang_tag = f"[{art.get('language', 'en').upper()}]"
            lines.append(
                f"[{i}] {lang_tag} {art['title']}\n"
                f"    Source: {art.get('source', 'Unknown')}\n"
                f"    Snippet: {art.get('snippet', '')[:300]}"
            )
        return "Articles to analyze:\n\n" + "\n\n".join(lines)

    def _parse_llm_response(self, text: str) -> list[dict]:
        """Extract JSON array from LLM response, handling markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            log.warning(f"Failed to parse LLM JSON: {e}\nResponse: {text[:500]}")
            return []

    async def score_and_summarize(
        self,
        articles: list[dict],
        min_score: int = 5,
        max_articles: int = 15,
    ) -> list[dict]:
        """Score and summarize articles in batches. Returns top articles."""

        all_scored = []
        batch_num = 0
        total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

        for i in range(0, len(articles), BATCH_SIZE):
            batch = articles[i : i + BATCH_SIZE]
            prompt = self._build_batch_prompt(batch)
            batch_num += 1

            if batch_num > 1:
                await asyncio.sleep(2)

            log.info(f"LLM batch {batch_num}/{total_batches}...")

            success = False
            for attempt in range(3):
                try:
                    response_text = await self._call_llm(prompt)
                    log.info(f"LLM response preview: {response_text[:200]}")
                    results = self._parse_llm_response(response_text)
                    log.info(f"Parsed {len(results)} results, scores: {[r.get('relevance', '?') for r in results[:5]]}")
                    success = True

                    for result in results:
                        idx = result.get("id", -1)
                        if 0 <= idx < len(batch):
                            batch[idx]["relevance_score"] = result.get("relevance", 0)
                            batch[idx]["summary"] = result.get("summary") or ""
                            if batch[idx]["relevance_score"] >= min_score:
                                all_scored.append(batch[idx])

                    break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        wait = 10 * (attempt + 1)
                        log.warning(f"Rate limited on batch {batch_num}, waiting {wait}s (attempt {attempt+1}/3)")
                        await asyncio.sleep(wait)
                    else:
                        log.error(f"LLM batch {batch_num} failed: {e}")
                        break
                except Exception as e:
                    log.error(f"LLM batch {batch_num} failed: {e}")
                    break

            if not success:
                for art in batch:
                    art["relevance_score"] = art.get("keyword_score", 0)
                    if art["relevance_score"] >= min_score:
                        all_scored.append(art)

        # Sort by relevance, take top N
        all_scored.sort(key=lambda a: a["relevance_score"], reverse=True)
        return all_scored[:max_articles * 2]

    async def generate_daily_brief(self, articles: list[dict]) -> str:
        """Generate a strategic daily brief in English based on today's top articles."""
        if not articles:
            return (
                "📋 <b>Summary</b>\n\n"
                "No relevant news today."
            )

        articles_text = ""
        for i, art in enumerate(articles[:15]):
            score = art.get("relevance_score", 0)
            summary = art.get("summary", "")
            articles_text += (
                f"{i+1}. [{score}/10] {art.get('title', '')}\n"
                f"   Summary: {summary}\n"
                f"   Source: {art.get('source', '')}\n\n"
            )

        prompt = DAILY_BRIEF_PROMPT.format(articles_text=articles_text)

        try:
            brief_text = await self._call_llm(
                prompt,
                system="You are a news analyst for Rhino, an armored ride-hailing startup in Brazil. You want them to success and at the very least sell the company at the unicorn level. Your job: evaluate each article's relevance and write a short concise summary for the founders' daily digest in English. IMPORTANT: Do NOT use any Markdown formatting (no **, no *, no #, no ```) or CAPSLOCK in summaries."
            )
            return f"📋 <b>Summary</b>\n\n{brief_text.strip()}"
        except Exception as e:
            log.error(f"Failed to generate daily brief: {e}")
            high = [a for a in articles if a.get("relevance_score", 0) >= 8]
            if high:
                lines = ["📋 <b>Summary</b>\n"]
                lines.append(f"{len(high)} news found:")
                for a in high[:5]:
                    lines.append(f"• {a.get('title', '')[:80]}")
                return "\n".join(lines)
            return "📋 <b>Summary</b>\n\nNo relevant news today."
