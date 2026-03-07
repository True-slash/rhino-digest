"""
Telegram Bot API sender.
Sends HTML-formatted messages with link preview disabled.
"""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class TelegramSender:
    def __init__(self, token: str):
        self.token = token

    def _url(self, method: str) -> str:
        return TELEGRAM_API.format(token=self.token, method=method)

    async def send(self, chat_id: str, text: str) -> bool:
        """Send a message to a Telegram chat. Returns True on success."""
        import re

        async with httpx.AsyncClient(timeout=30) as client:
            # Try HTML first
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            resp = await client.post(self._url("sendMessage"), json=payload)

            if resp.status_code == 200:
                return True

            # HTML failed — strip all tags and send plain text
            log.warning(f"HTML send failed ({resp.status_code}), falling back to plain text")
            plain = text
            plain = re.sub(r'<a href="[^"]*">(.*?)</a>', r'\1', plain)
            for tag in ["b", "i", "code", "blockquote"]:
                plain = plain.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
            plain = plain.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')

            payload2 = {
                "chat_id": chat_id,
                "text": plain,
                "disable_web_page_preview": True,
            }
            resp2 = await client.post(self._url("sendMessage"), json=payload2)
            if resp2.status_code == 200:
                log.info("Plain text fallback succeeded")
                return True

            log.error(f"Plain text also failed: {resp2.text}")
            return False

    async def get_updates(self) -> list[dict]:
        """Fetch recent updates (useful for getting chat_id on first setup)."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._url("getUpdates"))
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", [])
