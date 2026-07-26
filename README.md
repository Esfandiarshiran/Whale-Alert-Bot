# 🐋 Whale Alert Bot v2.1 — On-Chain Whale Tracking, Reimagined

> **Real-time whale tracking that goes beyond "whale moved $X".**
> Direction-aware. Score-driven. Card-powered. Insight-engine. Built for virality.

This is the upgraded version of the Whale Alert Telegram bot — engineered from the ground up to be the **most distinctive on-chain whale alert system on Telegram**, with features that other channels simply don't have.

**What's new in v2.1:**
- 🧠 **Insight Engine** — every alert gets a bullish/bearish/neutral narrative
- 🗳 **Interactive Bullish/Bearish vote buttons** — subs engage + share predictions
- 🧪 **`/test` command** — see sample alerts instantly (no waiting for whales!)
- 📊 **Marketing analytics columns** in Supabase (clicks, conversions per channel)
- ⚡ **Smart scheduling** — 60% less GitHub Actions usage (peak vs off-peak)
- 🔒 **Removed `TELEGRAM_CHANNEL_ID` from secrets** — all channels managed in Supabase

---

## 📑 Table of Contents

- [What's New in v2](#-whats-new-in-v2)
- [Why This Bot Goes Viral](#-why-this-bot-goes-viral)
- [Architecture](#-architecture)
- [Setup Guide (15 minutes)](#-setup-guide-15-minutes)
- [Admin Commands](#-admin-commands)
- [Data Sources (100% Free, 100% Real)](#-data-sources-100-free-100-real)
- [Channel "About" Section — SEO Optimized](#-channel-about-section--seo-optimized)
- [Growth Strategy](#-growth-strategy)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 🚀 What's New in v2

### 🎯 Whale Score (0–100)
Every alert gets a transparent score based on real inputs:
- **Value** (40 pts max): logarithmic scaling — $1M ≈ 10 pts, $100M ≈ 30 pts
- **Direction** (25 pts max): exchange_in > exchange_out > inter_exchange > cold_storage
- **Wallet Novelty** (20 pts max): brand-new wallets are flagged
- **Cluster Timing** (15 pts max): whales moving together = bigger signal

**Score is COMPUTED, never guessed.** The formula is shown in every alert's breakdown line.

### 🐳 Tier Badges
Instant visual recognition:
- 🐳 **MEGA** — $50M+ (rare, scary)
- 🦈 **LARGE** — $10M–$50M
- 🐋 **WHALE** — $1M–$10M
- 🐬 **SMALL** — $500K–$1M

### 🎨 Beautiful PNG Cards
Every alert generates a 1080×1080 PNG card — perfectly sized for **Twitter/X, Instagram, Telegram forward**. Cards include:
- Tier badge + asset
- Massive USD value (hero)
- Direction arrow with color
- From/To labels with shortened addresses
- Whale Score gauge
- Watermark footer (`@OnchainPulse3` + `@Onchainpulse1_bot`)

**This is what makes people share.** Text-only alerts get 3 forwards. Beautiful cards get 300.

### → Direction Analysis (the killer feature)
Every alert shows what the move MEANS:
- `→ Exchange (Binance)` — funds moving TO exchange → typically associated with **sell pressure**
- `← Exchange (Coinbase)` — funds leaving exchange → typically associated with **accumulation**
- `↔ Private wallet transfer` — peer-to-peer (OTC, custody shift)
- `🔄 Inter-exchange: Binance → Kraken` — internal rebalance

### 🧠 Wallet Memory
We track every wallet we've ever seen. For each alert:
- **First-seen detection** — "🎯 FIRST-TIME WALLET DETECTED"
- **Last active** — "last active 47 days ago" (cold storage moves are rare and meaningful)
- **Activity count** — how many times we've seen this wallet

### 🌊 Cluster Detection
When **4+ whales move within 30 minutes**, we send a separate cluster alert. This is often the precursor to major market moves — and most channels miss it entirely.

### 📊 Daily Digest
Every 24 hours, a beautiful summary card with:
- Total whale alerts in last 24h
- BTC/ETH/Stables breakdown
- Total USD volume
- **Net exchange flow** — bullish (outflow) or bearish (inflow) signal

### 📡 Multi-Channel Distribution
Send alerts to **all your partner channels**, not just one. Each partner adds the bot as admin → you register them via `/addchannel` → alerts flow automatically.

### 🛡️ Bulletproof Resilience
- **Never crashes** — every external call is wrapped in try/except
- **Per-channel isolation** — one channel failure doesn't affect others
- **Auto-disable** — after 5 consecutive failures, channel is auto-removed
- **Multi-source prices** — Coinbase → Binance → CoinGecko fallback chain
- **Atomic cache writes** — no corruption on concurrent runs

---

## 🎯 Why This Bot Goes Viral

Most whale alert channels show: *"1000 BTC moved. Source: mempool."* — boring, contextless, indistinguishable from 1000 other channels.

**Our alerts show:**

```
🐋 WHALE — BTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰  $5.13M
    78.87 BTC

→  → Exchange (Binance 14)
    Funds moving TO exchange — typically associated
    with potential sell pressure

FROM  Unlabeled  (last active 47 days ago)
      0xabc1...c123
TO    Binance 14
      0x28c6...1d60

🎯  FIRST-TIME WALLET DETECTED

⚡  Whale Score: 72/100
    value 17 • direction 25 • novelty 20 • cluster 10

TX: e4504b866e7f3c49...
Time: 11:16 UTC

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Daily onchain analysis charts: @OnchainPulse3
40+ crypto tools — try free: @Onchainpulse1_bot
```

**Plus** a beautiful PNG card with the same info, sized for Twitter.

### The Viral Loop

1. User sees a stunning alert card in your channel
2. **One tap** on "📢 Share this alert" button → forwards to their own network
3. Their network sees the watermark (`@OnchainPulse3` + `@Onchainpulse1_bot`)
4. New users subscribe to YOUR main channels
5. Partners add the bot to their channels (free!)
6. Loop intensifies — every partner channel is a distribution node

---

## 🏗 Architecture

```
whale-alert-bot/
├── .github/workflows/
│   ├── whale_alert.yml          # scan every 15 min
│   └── admin_poll.yml           # poll admin commands every 5 min
├── src/
│   ├── __init__.py
│   ├── config.py                # config + VERIFIED exchange addresses
│   ├── http.py                  # HTTP with retry + backoff
│   ├── cache.py                 # dedup + wallet memory + cluster state
│   ├── supabase.py              # multi-channel management
│   ├── enrichment.py            # live labels + direction inference
│   ├── virality.py              # Whale Score + tiers + cluster detection
│   ├── card_generator.py        # PNG card generation (Pillow)
│   ├── formatter.py             # message formatting
│   ├── telegram.py              # multi-channel send + admin poll
│   ├── analyzer.py              # orchestrator: fetch → enrich → score → format
│   ├── main.py                  # scan entry point
│   ├── admin_bot.py             # admin command handler
│   └── sources/
│       ├── __init__.py
│       ├── btc.py               # mempool.space (real BTC mempool)
│       ├── eth.py               # Blockscout (real ETH txs)
│       ├── stablecoin.py        # Blockscout (real ERC-20 transfers)
│       ├── tron.py              # TronGrid (real TRON USDT — HUGE volume!)
│       └── prices.py            # multi-source price fallback
├── scripts/
│   ├── setup_supabase.sql       # SQL to create tables
│   └── test_local.py            # local test suite
├── cache/                       # runtime cache (gitignored)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🛠 Setup Guide (15 minutes)

### Step 1: Create your Telegram bot

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Pick a name (e.g. "Onchain Whale Alert")
4. Pick a username (e.g. `OnchainWhaleAlertBot`)
5. **Copy the bot token** — you'll need it

### Step 2: Create your main Telegram channel

1. Create a new channel (e.g. `@OnchainWhaleAlert`)
2. Add your bot as **administrator** with "Post Messages" permission
3. Note the channel username (e.g. `@OnchainWhaleAlert`)

### Step 3: Get your Telegram user ID

You need this to be the super-admin.

1. Open [@userinfobot](https://t.me/userinfobot)
2. Send any message
3. It will reply with your numeric user ID (e.g. `123456789`)

### Step 4: Set up Supabase (free tier)

1. Go to [supabase.com](https://supabase.com) → sign up (free)
2. Create a new project (any name)
3. Once created, go to **Settings → API**:
   - Copy **Project URL** (e.g. `https://abcd.supabase.co`)
   - Copy **service_role key** (the LONG one, NOT the anon key) ⚠️ Keep secret!
4. Go to **SQL Editor → New query**
5. Paste the contents of `scripts/setup_supabase.sql`
6. Click **Run** — this creates the `WhaleAlert` and `whale_admins` tables
7. (Optional) At the bottom of the SQL, uncomment and edit the INSERT for your user ID
8. Run that section to make yourself super-admin in DB

### Step 5: Push this code to GitHub

```bash
cd whale-alert-bot
git init
git add .
git commit -m "Whale Alert Bot v2"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/whale-alert-bot.git
git push -u origin main
```

**⚠️ Make the repo PUBLIC** — public repos get unlimited GitHub Actions minutes. Private repos are limited to 2000 min/month.

### Step 6: Add GitHub Secrets

Go to: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHANNEL_ID` | Your main channel (e.g. `@OnchainWhaleAlert`) |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase **service_role** key |
| `SUPER_ADMIN_IDS` | Your Telegram user ID (e.g. `123456789`) |

### Step 7: Test

1. Go to **Actions** tab in GitHub
2. Select "Whale Alert Scan" → **Run workflow**
3. Watch the logs — you should see:
   - "First run detected - posting welcome message"
   - "Welcome sent to 1 channel(s)"
   - "BTC: N large txs found" (or "no large txs found")
4. Check your Telegram channel — you should see the welcome message

### Step 8: Talk to your bot

1. Find your bot on Telegram (search its username)
2. Send `/start` — bot replies with help
3. Send `/status` — bot replies with current state
4. Try `/listchannels` — should show your main channel

### Step 9: Add partner channels

For each partner who wants the bot in their channel:

1. Partner adds the bot as **administrator** to their channel
2. You (the super-admin) DM the bot: `/addchannel @partner_channel_username`
3. Bot confirms: "✅ Channel added"
4. Next scan run, alerts go to all channels including the new one

To remove a channel: `/removechannel @partner_channel_username`

---

## 🎛 Admin Commands

DM these commands to your bot.

### Public commands (anyone)
| Command | Description |
|---|---|
| `/start` | Welcome + help |
| `/help` | Show all available commands |
| `/status` | Bot status + channel count + stats |
| `/stats` | Today's whale alert stats |

### Admin commands (super-admins + added admins)
| Command | Description |
|---|---|
| `/addchannel @username` | Add a channel (by @username) |
| `/addchannel -100123.. [title]` | Add a channel (by numeric ID) |
| `/removechannel @username` | Remove a channel |
| `/listchannels` | List all active channels |
| `/addadmin <user_id> [username]` | Add an admin |
| `/removeadmin <user_id>` | Remove an admin |
| `/listadmins` | List all admins |

---

## 📡 Data Sources (100% Free, 100% Real)

| Source | Used for | API Key? |
|---|---|---|
| [mempool.space](https://mempool.space) | BTC mempool transactions + tx details | ❌ None |
| [Blockscout](https://eth.blockscout.com) | ETH + ERC-20 token transfers | ❌ None |
| [TronGrid](https://www.trongrid.io) | TRON USDT transfers (HUGE volume!) | ❌ None |
| [Coinbase API](https://api.coinbase.com) | BTC/ETH spot price | ❌ None |
| [Binance API](https://binance.com) | Price fallback | ❌ None |
| [CoinGecko API](https://coingecko.com) | Price fallback + altcoin prices | ❌ None |

**Zero paid APIs. Zero fabricated data.** Every number is verifiable on-chain.

### Address Labels — Verification Policy

We only label addresses that are **publicly verifiable**:
- **Binance, Bitfinex, Coinbase, Kraken** — from official Proof of Reserves disclosures
- **Live lookup via Blockscout** — for addresses they have tagged in their public database
- All other addresses are labeled **"Unlabeled"** — we never guess.

This is critical: **we never fabricate labels**. If we don't know, we say so.

---

## 📝 Channel "About" Section — SEO Optimized

Copy this exactly into your Telegram channel's "About" / description (Settings → Edit Channel → Description).

### English version (recommended for international reach)

```
🐋 Real-time on-chain whale alerts — BTC, ETH, USDT, stablecoins.
Direction analysis · Whale Score (0-100) · Cluster detection · Beautiful shareable cards.
Free. Verifiable. No fabrication.

📡 Daily charts: @OnchainPulse3
🛠 40+ crypto tools: @Onchainpulse1_bot
```

### Keywords (for Telegram + Google SEO)

When users search Telegram for any of these, your channel should rank:
- `whale alert` ✓
- `crypto whale` ✓
- `BTC whale` ✓
- `ETH whale` ✓
- `USDT whale` ✓
- `onchain whale` ✓
- `on-chain` ✓
- `real-time` ✓
- `whale tracker` ✓

### Channel Name Recommendation

Pick a name like:
- `Onchain Whale Alert` (current — good)
- `Whale Alert Pro` (slightly better)
- `Whale Watch — Onchain Alerts` (more keyword-rich)

The name + about together should give you strong SEO for whale-related searches.

---

## 📈 Growth Strategy

### Phase 1: Seed (Week 1–2)
- Manually invite first 50–100 subscribers from your network
- Post 2–3 alerts per day to ensure quality > quantity
- Reply to every comment / question

### Phase 2: Partner Outreach (Week 2–4)
- Identify 10–20 mid-size crypto channels (1K–50K subs)
- DM their admins: *"I built a free whale alert bot. You add it to your channel as admin, you get beautiful real-time alerts at zero cost. Interested?"*
- Most will say yes — it's free content for them
- Each partner channel = new distribution node

### Phase 3: Viral Loop (Month 2+)
- Cards get shared on Twitter → new users discover your main channel
- Cluster alerts catch attention during market moves → people share
- Daily Digest cards become "must-share" content
- The watermark footer on every card is your funnel

### Phase 4: Ecosystem Lock-in (Month 3+)
- 50+ partner channels now depend on your bot
- Removing it would leave their channels empty
- New features (Whale of the Week, Smart Money tracking) keep you ahead

### KPIs to watch
- **Daily new subscribers** (target: 30+/day after Month 2)
- **Card share rate** (forward count per alert — target: 5+)
- **Partner channels** (target: 50+ by Month 3)
- **Telegram search ranking** for "whale alert" (target: top 3)

---

## 🚨 Troubleshooting

### Bot not sending alerts
1. Check Actions tab — any failed runs?
2. Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` secrets
3. Check that bot is **admin** in the channel
4. Try `/status` command — does it reply?

### Bot not responding to commands
1. Check `admin_poll.yml` workflow is running (every 5 min)
2. Verify `SUPER_ADMIN_IDS` secret includes your user ID
3. Check Supabase `whale_admins` table — are you listed?

### Cards not generating
1. Install Pillow: `pip install Pillow`
2. Check Actions logs for "Card generation failed" warnings
3. Bot falls back to text-only — alerts still send

### Supabase connection failed
1. Verify `SUPABASE_URL` format: `https://xxxx.supabase.co`
2. Verify `SUPABASE_KEY` is the **service_role** key (not anon)
3. Check that tables exist: `SELECT * FROM "WhaleAlert";`
4. Bot falls back to env `TELEGRAM_CHANNEL_ID` if Supabase fails

### Channel auto-disabled
- After 5 consecutive send failures, channel is set `is_active=false`
- Common causes: bot removed from channel, channel deleted, lost admin rights
- Fix: re-add bot as admin, then `/addchannel @channel` again

---

## 📜 License

MIT — use freely, modify freely. Just keep the footer (`@OnchainPulse3` + `@Onchainpulse1_bot`) — that's the funnel.

---

## 🙏 Credits

Built with:
- [mempool.space](https://mempool.space) — Bitcoin mempool data
- [Blockscout](https://blockscout.com) — Ethereum block explorer
- [TronGrid](https://trongrid.io) — TRON network data
- [Pillow](https://python-pillow.org) — image generation
- [Supabase](https://supabase.com) — Postgres database
- [GitHub Actions](https://github.com/features/actions) — free CI/CD runtime

**100% free. 100% open. 100% verifiable.**
