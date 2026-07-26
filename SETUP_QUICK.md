# ⚡ Quick Setup (10 minutes)

You already have the bot running on GitHub Actions. Here's how to upgrade to v2.1.

## Step 1: Get your Supabase credentials

1. Go to [supabase.com](https://supabase.com) → sign in (free account)
2. Click **New Project** → name it `whale-alert` → pick a strong DB password
3. Wait ~2 minutes for provisioning
4. Go to **Settings → API**:
   - Copy **Project URL** (looks like `https://abc123xyz.supabase.co`)
   - Copy **service_role key** (the LONG one — NOT anon)

## Step 2: Create the tables

1. In Supabase dashboard, go to **SQL Editor → New query**
2. Open `scripts/setup_supabase.sql` from this repo
3. Copy everything → paste into Supabase SQL Editor
4. Click **Run** → you should see "Success. No rows returned"
5. **IMPORTANT:** Scroll to the bottom of the SQL. Uncomment the two INSERT statements:
   - Edit the first INSERT: replace `123456789` with your real Telegram user ID
   - Edit the second INSERT: replace `@YourMainChannel` with your actual channel @username
   - Run those two INSERTs separately
6. Verify with: `SELECT * FROM v_active_channels;` — should show `active_count = 1`

## Step 3: Add GitHub Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

You need these 4 secrets (you can REMOVE the old `TELEGRAM_CHANNEL_ID` — channels now come from Supabase):

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `SUPABASE_URL` | Your Supabase Project URL |
| `SUPABASE_KEY` | Your Supabase service_role key (the LONG one) |
| `SUPER_ADMIN_IDS` | Your Telegram user ID (just the number, no @) |

## Step 4: Replace the code

1. Delete all files in your existing GitHub repo EXCEPT `.git/`
2. Upload all files from this `whale-alert-bot/` folder
3. Commit and push

## Step 5: Verify

1. Go to **Actions** tab → **"Whale Alert Bot"** → **Run workflow**
2. Watch the logs — you should see:
   ```
   ADMIN BOT - polling for commands
   No new updates
   
   WHALE ALERT BOT v2 - Starting scan
   Channels configured: 1
   Prices: BTC=$X  ETH=$Y
   Sending to 1 channel(s)
   ```
3. Check your Telegram channel — you should see a welcome message

## Step 6: Test the bot IMMEDIATELY (no waiting for whales!)

DM your bot:
```
/test
```

The bot will reply: "🧪 Generating TEST alert(s)..." then post a beautiful sample alert to your channel using REAL latest transactions. You can see exactly what alerts look like RIGHT NOW.

You can also test specific sources:
- `/test btc` — only BTC
- `/test eth` — only ETH
- `/test tron` — only TRON USDT
- `/test all` — all three

## Step 7: Talk to your bot

1. Find your bot in Telegram → send `/start`
2. Send `/help` — should show all commands
3. Send `/status` — should show "Active channels: 1"
4. Send `/listchannels` — should show your main channel

## Step 8: Add partner channels

For each partner who wants the bot:

1. **Partner** adds your bot as administrator to their channel (only "Post Messages" permission needed)
2. **You** DM your bot: `/addchannel @partner_channel_username`
3. Bot replies: `✅ Channel added`
4. Done! Next scan, alerts flow to all channels including the new one

To remove a channel: `/removechannel @partner_channel_username`

---

## 🆘 Troubleshooting

**Bot not sending alerts?**
- Check Actions tab for failed runs
- Verify all 4 secrets are set correctly
- Check that your main channel is in Supabase: `SELECT * FROM "WhaleAlert" WHERE is_active = true;`
- Check that bot is admin in the channel
- Try `/test` to see if a test alert sends

**Bot not responding to commands?**
- Verify `SUPER_ADMIN_IDS` is your numeric Telegram ID (no @ symbol)
- The workflow runs every 10 min during peak hours — wait up to 10 min
- Check Actions tab → workflow is running
- Make sure you started a private chat with the bot first (send `/start`)

**Cards not generating?**
- Pillow should auto-install via `requirements.txt`
- Check Actions logs for "Card generation failed" warnings
- Bot falls back to text-only — alerts still send

**Supabase connection failed?**
- Verify URL format: `https://xxxx.supabase.co` (no trailing slash)
- Use service_role key, NOT anon key
- Check tables exist: `SELECT * FROM "WhaleAlert";`
- After v2.1, there's NO env fallback — channels MUST come from Supabase

**Channel auto-disabled?**
- After 5 consecutive send failures, channel is set `is_active=false`
- Common causes: bot removed from channel, channel deleted, lost admin rights
- Fix: re-add bot as admin, then `/addchannel @channel` again

---

## 🎯 You're done!

Your bot is now running v2.1 with:
- ✅ Beautiful PNG cards with market context narrative
- ✅ Insight Engine (bullish/bearish/caution analysis per alert)
- ✅ Interactive Bullish/Bearish vote buttons (sub engagement)
- ✅ Whale Score + tier badges + cluster detection
- ✅ Multi-channel distribution via Supabase
- ✅ `/test` command for instant preview
- ✅ Smart scheduling (60% less GitHub Actions usage)
- ✅ Marketing analytics columns ready for future tracking

Next steps:
1. Run `/test` to see a sample alert immediately
2. Update your channel **About** with the SEO text from `scripts/channel_about.md`
3. Pin the welcome message
4. Start partner outreach using messages in `scripts/outreach_messages.md`
5. Post your card on Twitter/X to start the viral loop

## 📊 Smart Scheduling Explained

The workflow runs:
- **Every 10 min** during UTC 06:00-22:00 (peak whale activity)
- **Every 30 min** during UTC 22:00-06:00 (low activity, save resources)

Total: ~128 runs/day = ~3,840 runs/month for this bot.
Each run ~30s = ~64 min/day = ~1,920 min/month.

**For public repos, GitHub Actions is unlimited** — so even with 7 bots on your account, you're nowhere near limits. But smart scheduling means faster responses during peak hours and less waste at night.
