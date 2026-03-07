# 🦏 Rhino Daily News Digest Bot

AI-powered daily news digest for ride-hailing & urban mobility — delivered to Telegram every morning.

## What it does

1. **Fetches** 200+ articles from Google News RSS (EN + PT-BR) and direct outlet feeds
2. **Deduplicates** by URL and fuzzy title matching
3. **Pre-filters** with weighted keyword scoring (free, fast)
4. **Scores & summarizes** with LLM (Groq free tier / Claude / Gemini)
5. **Delivers** a formatted digest to Telegram
6. **Runs on GitHub Actions** — zero cost, zero infrastructure

## Quick Start (15 minutes)

### 1. Create Telegram Bot

- Message **@BotFather** on Telegram → `/newbot`
- Save the API token
- Send `/start` to your new bot

### 2. Get your Chat ID

```bash
export TELEGRAM_BOT_TOKEN=your_token_here
cd src && python get_chat_id.py
```

### 3. Get a free Groq API key

- Go to [console.groq.com](https://console.groq.com/keys)
- Create a free API key (no credit card needed)

### 4. Set up GitHub repo

```bash
# Fork or push this project to GitHub (PUBLIC repo for free Actions)
git init && git add . && git commit -m "init"
gh repo create rhino-news-bot --public --push
```

### 5. Add secrets to GitHub

Go to repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_IDS` | Comma-separated chat IDs |
| `LLM_PROVIDER` | `groq` |
| `LLM_API_KEY` | Your Groq API key |
| `LLM_MODEL` | `llama-3.3-70b-versatile` |

### 6. Test it

Go to Actions tab → "Daily News Digest" → "Run workflow" → Run.

That's it! The bot will now run every day at 7:00 AM São Paulo time.

## Customization

### Add/remove RSS feeds

Edit `src/fetcher.py` — the `GOOGLE_NEWS_FEEDS` and `DIRECT_FEEDS` dictionaries.

Google News query tips:
- Use `OR` between terms: `Uber+OR+Lyft+OR+Bolt`
- Target outlets: `site:techcrunch.com+ride-hailing`
- Filter by date: `after:2024-01-01`

### Tune relevance

- `src/filter.py` — keyword lists and weights
- `src/summarizer.py` — LLM system prompt
- `.env` / GitHub secrets — `MIN_RELEVANCE` (default 5), `MAX_ARTICLES` (default 15)

### Switch LLM provider

| Provider | Cost | Setup |
|---|---|---|
| **Groq** | Free (1000 req/day) | [console.groq.com](https://console.groq.com) |
| **Gemini** | Free (1000 req/day) | [aistudio.google.com](https://aistudio.google.com/apikey) |
| **Anthropic** | ~$0.90/mo | [console.anthropic.com](https://console.anthropic.com) |

Set `LLM_PROVIDER` and `LLM_API_KEY` accordingly.

### Change schedule

Edit `.github/workflows/daily-news.yml`:

```yaml
schedule:
  - cron: '0 10 * * *'    # 10:00 UTC = 07:00 BRT
  - cron: '0 10 * * 1-5'  # Weekdays only
  - cron: '0 12 * * *'    # Noon UTC
```

## Architecture

```
Fetch (parallel async)  →  Deduplicate  →  Keyword filter  →  LLM score  →  Format  →  Telegram
     ~5 sec                  ~instant        ~instant          ~10 sec      ~instant     ~1 sec
```

Total execution: **~20 seconds** per run.

## Cost

| Component | Monthly cost |
|---|---|
| GitHub Actions | $0 (public repo) |
| Google News RSS | $0 |
| Groq LLM API | $0 (free tier) |
| Telegram Bot API | $0 |
| **Total** | **$0** |
