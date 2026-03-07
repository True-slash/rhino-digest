"""
Helper: Get your Telegram chat_id.

Usage:
  1. Create bot via @BotFather on Telegram
  2. Send /start to your new bot
  3. Run: TELEGRAM_BOT_TOKEN=your_token python get_chat_id.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sender import TelegramSender


async def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN env variable first!")
        print("  export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...")
        return

    sender = TelegramSender(token)
    updates = await sender.get_updates()

    if not updates:
        print("No updates found.")
        print("Make sure you sent /start to your bot first!")
        return

    print("\nFound chats:\n")
    seen = set()
    for update in updates:
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            chat_type = chat.get("type", "unknown")
            name = (
                chat.get("title")
                or f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
            )
            print(f"  Chat ID: {chat_id}")
            print(f"  Name:    {name}")
            print(f"  Type:    {chat_type}")
            print()

    print("Add these chat IDs to TELEGRAM_CHAT_IDS (comma-separated)")
    print(f'  e.g.: TELEGRAM_CHAT_IDS="{",".join(str(c) for c in seen)}"')


if __name__ == "__main__":
    asyncio.run(main())
