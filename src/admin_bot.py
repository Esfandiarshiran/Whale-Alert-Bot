"""
Admin command processor.
Polls Telegram getUpdates and processes commands.

Handles:
- /start [spot_TXID] — welcome OR personalization deep link
- /help, /status, /stats — info commands
- /addchannel, /removechannel, /listchannels — admin channel management
- /addadmin, /removeadmin, /listadmins — admin user management
- /test [btc|eth|tron] — generate sample alert
- Free text messages — if user has pending personalization, treat as username

CRITICAL: Only super-admins (env) and admins (Supabase) can run privileged commands.
The /start spot_TXID flow is OPEN TO EVERYONE (that's the viral mechanic).
Security: never trust user input - validate all arguments.
"""
import sys
import time
import json
from .telegram import (
    get_updates, send_admin_reply, build_share_buttons,
    build_personalized_card_buttons, build_twitter_intent_url,
)
from .cache import (
    get_update_offset, set_update_offset, get_stats, diagnostics,
    set_pending_personalization, get_pending_personalization,
    clear_pending_personalization, get_alert_meta,
)
from .supabase import (
    list_channels, add_channel, remove_channel, get_channel_count,
    is_admin, list_admins, add_admin, remove_admin,
)
from .config import SUPER_ADMIN_IDS, FOOTER_TEXT, FOOTER_MAIN_BOT, FOOTER_MAIN_CHANNEL, log
from .formatter import format_help_message, format_status_message


# Commands that require admin
ADMIN_COMMANDS = {'/addchannel', '/removechannel', '/listchannels',
                  '/addadmin', '/removeadmin', '/listadmins', '/test'}


def handle_command(update: dict) -> None:
    """Process a single Telegram update (message)."""
    try:
        message = update.get('message') or {}
        if not message:
            return

        chat_id = message.get('chat', {}).get('id')
        if not chat_id:
            return

        text = (message.get('text') or '').strip()
        if not text:
            return

        user = message.get('from') or {}
        user_id = str(user.get('id', ''))
        username = user.get('username', '') or user.get('first_name', '')

        # === Check if user has a pending personalization ===
        # If so, treat their message as the username for the card
        pending = get_pending_personalization(user_id)
        if pending and not text.startswith('/'):
            _handle_personalization_response(chat_id, user_id, text, pending)
            return

        # Parse command + args
        parts = text.split()
        if not parts:
            return
        cmd = parts[0].lower().split('@')[0]  # strip bot mention
        args = parts[1:]

        log.info(f"Command from {user_id} ({username}): {cmd} {args[:2]}")  # don't log full args (privacy)

        # === /start with deep link (personalization flow) ===
        if cmd == '/start':
            if args and args[0].startswith('spot_'):
                # Deep link: /start spot_TXIDSHORT
                txid_short = args[0][5:]  # remove "spot_" prefix
                _handle_spot_request(chat_id, user_id, txid_short)
                return
            elif args and args[0] == 'help':
                send_admin_reply(chat_id, format_help_message(is_admin=is_admin(user_id)))
                return
            else:
                # Plain /start
                _handle_start(chat_id, user_id, username)
                return

        if cmd == '/help':
            send_admin_reply(chat_id, format_help_message(is_admin=is_admin(user_id)))
            return

        if cmd == '/spot' and args:
            # Direct /spot command: /spot TXIDSHORT
            _handle_spot_request(chat_id, user_id, args[0])
            return

        if cmd == '/status':
            stats = get_stats()
            diag = diagnostics()
            send_admin_reply(chat_id, format_status_message(get_channel_count(), stats, diag))
            return

        if cmd == '/stats':
            stats = get_stats()
            divider = "━" * 30
            today_msg = (
                f"📊  TODAY'S WHALE STATS\n"
                f"{divider}\n"
                f"BTC alerts: {stats.get('btc', 0)}\n"
                f"ETH alerts: {stats.get('eth', 0)}\n"
                f"Stable alerts: {stats.get('stable', 0)}\n"
                f"Total: {stats.get('total', 0)}\n\n"
                f"Channels: {get_channel_count()}\n\n"
                f"{divider}\n"
                f"{FOOTER_TEXT}"
            )
            send_admin_reply(chat_id, today_msg)
            return

        # Admin-only commands
        if cmd in ADMIN_COMMANDS:
            if not is_admin(user_id):
                send_admin_reply(chat_id, "⛔  Access denied. You are not an admin.")
                log.warning(f"Non-admin {user_id} tried {cmd}")
                return

            if cmd == '/addchannel':
                _cmd_add_channel(chat_id, args, user_id)
            elif cmd == '/removechannel':
                _cmd_remove_channel(chat_id, args, user_id)
            elif cmd == '/listchannels':
                _cmd_list_channels(chat_id)
            elif cmd == '/addadmin':
                _cmd_add_admin(chat_id, args, user_id)
            elif cmd == '/removeadmin':
                _cmd_remove_admin(chat_id, args, user_id)
            elif cmd == '/listadmins':
                _cmd_list_admins(chat_id)
            elif cmd == '/test':
                _cmd_test(chat_id, args)
            return

        # Unknown command
        send_admin_reply(chat_id, f"Unknown command: {cmd}\n\nUse /help to see available commands.")

    except Exception as e:
        log.exception(f"Command handling error: {e}")
        try:
            send_admin_reply(chat_id, "⚠️  Internal error processing command.")
        except Exception:
            pass


# =====================================================================
# ADMIN COMMAND HANDLERS
# =====================================================================
def _cmd_add_channel(chat_id: str, args: list, added_by: str) -> None:
    """Usage: /addchannel @username  OR  /addchannel -1001234567890 [title]"""
    if not args:
        send_admin_reply(chat_id,
            "Usage:\n"
            "  /addchannel @username\n"
            "  /addchannel -1001234567890 [title]\n\n"
            "Make sure the bot is added as ADMIN to the channel first.")
        return

    channel = args[0]
    title = ' '.join(args[1:]) if len(args) > 1 else ''

    # Validate
    if not (channel.startswith('@') or channel.startswith('-100')):
        send_admin_reply(chat_id, "Channel must start with @ or -100 (numeric ID).")
        return

    result = add_channel(
        channel_id=channel if channel.startswith('-100') else '',
        username=channel if channel.startswith('@') else '',
        title=title,
        added_by=added_by,
    )
    if result.get('ok'):
        send_admin_reply(chat_id,
            f"✅  Channel added: {channel}\n"
            f"Total channels: {get_channel_count()}\n\n"
            f"⚠️  Make sure the bot is ADMIN in that channel, otherwise sends will fail.\n"
            f"After 5 consecutive failures, the channel is auto-disabled.")
    else:
        send_admin_reply(chat_id, f"❌  Failed: {result.get('error', 'unknown error')}")


def _cmd_remove_channel(chat_id: str, args: list, removed_by: str) -> None:
    if not args:
        send_admin_reply(chat_id, "Usage: /removechannel @username  OR  /removechannel -1001234567890")
        return
    channel = args[0]
    result = remove_channel(channel)
    if result.get('ok'):
        send_admin_reply(chat_id, f"✅  Channel removed: {channel}\nTotal channels: {get_channel_count()}")
    else:
        send_admin_reply(chat_id, f"❌  Failed: {result.get('error', 'unknown error')}")


def _cmd_list_channels(chat_id: str) -> None:
    channels = list_channels(active_only=True)
    if not channels:
        send_admin_reply(chat_id, "No active channels.")
        return
    msg = f"📋  ACTIVE CHANNELS ({len(channels)})\n" + "━" * 30 + "\n"
    for i, c in enumerate(channels, 1):
        cid = c.get('channel_id') or '(no id)'
        uname = c.get('channel_username') or ''
        title = c.get('channel_title') or ''
        line = f"{i}. "
        if uname:
            line += f"{uname}"
        else:
            line += f"{cid}"
        if title:
            line += f"  ({title})"
        msg += line + "\n"
    msg += "\n" + FOOTER_TEXT
    send_admin_reply(chat_id, msg)


def _cmd_add_admin(chat_id: str, args: list, added_by: str) -> None:
    if not args:
        send_admin_reply(chat_id, "Usage: /addadmin <numeric_user_id> [username]")
        return
    new_admin_id = args[0]
    username = ' '.join(args[1:]) if len(args) > 1 else ''
    if not new_admin_id.isdigit():
        send_admin_reply(chat_id, "Telegram user ID must be numeric.")
        return
    result = add_admin(new_admin_id, username, added_by)
    if result.get('ok'):
        send_admin_reply(chat_id, f"✅  Admin added: {new_admin_id} ({username})")
    else:
        send_admin_reply(chat_id, f"❌  Failed: {result.get('error')}")


def _cmd_remove_admin(chat_id: str, args: list, removed_by: str) -> None:
    if not args:
        send_admin_reply(chat_id, "Usage: /removeadmin <numeric_user_id>")
        return
    target_id = args[0]
    if target_id in SUPER_ADMIN_IDS:
        send_admin_reply(chat_id, "❌  Cannot remove super-admin from env config.")
        return
    result = remove_admin(target_id)
    if result.get('ok'):
        send_admin_reply(chat_id, f"✅  Admin removed: {target_id}")
    else:
        send_admin_reply(chat_id, f"❌  Failed: {result.get('error')}")


def _cmd_list_admins(chat_id: str) -> None:
    admins = list_admins()
    msg = f"👥  ADMINS ({len(admins)})\n" + "━" * 30 + "\n"
    for i, a in enumerate(admins, 1):
        uid = a.get('telegram_user_id', '?')
        uname = a.get('username', '') or ''
        is_super = a.get('is_super_admin', False)
        marker = "👑" if is_super else "🛡"
        msg += f"{i}. {marker}  {uid}"
        if uname:
            msg += f"  (@{uname})"
        msg += "\n"
    msg += "\n" + FOOTER_TEXT
    send_admin_reply(chat_id, msg)


# =====================================================================
# TEST MODE COMMAND
# =====================================================================
def _cmd_test(chat_id: str, args: list) -> None:
    """Generate sample alert(s) using REAL latest transactions and post to all channels.
    Usage: /test [btc|eth|tron|all]"""
    source = args[0].lower() if args else 'all'
    if source not in ('btc', 'eth', 'tron', 'all'):
        send_admin_reply(chat_id, "Usage: /test [btc|eth|tron|all]")
        return

    send_admin_reply(chat_id, f"🧪 Generating TEST alert(s) from source: {source}\nThis takes ~30 seconds (fetching real latest txs)...")

    try:
        from .test_mode import build_test_alert_btc, build_test_alert_eth, build_test_alert_tron
        from .formatter import format_alert
        from .card_generator import generate_alert_card

        alerts = []
        if source in ('btc', 'all'):
            a = build_test_alert_btc()
            if a:
                alerts.append(a)
        if source in ('eth', 'all'):
            a = build_test_alert_eth()
            if a:
                alerts.append(a)
        if source in ('tron', 'all'):
            a = build_test_alert_tron()
            if a:
                alerts.append(a)

        if not alerts:
            send_admin_reply(chat_id, "❌  Could not generate test alerts (network issues or no recent txs).")
            return

        from .telegram import send_to_all_channels, build_share_buttons
        from .test_mode import TEST_MARKER

        sent_count = 0
        for alert in alerts:
            message = format_alert(alert)
            message = f"{TEST_MARKER}\n\n" + message
            photo_path = generate_alert_card(alert)
            # Get txid_short for personalization button
            full_txid = alert.get('tx_id', '')
            txid_short = None
            if full_txid:
                clean_txid = full_txid
                for prefix in ('btc_', 'eth_', 'stable_', 'trx_usdt_'):
                    if clean_txid.startswith(prefix):
                        clean_txid = clean_txid[len(prefix):]
                        break
                txid_short = clean_txid[:16] if clean_txid else None
            # Store meta for personalization
            if txid_short:
                try:
                    from .cache import store_alert_meta
                    store_alert_meta(txid_short, alert)
                except Exception:
                    pass
            # Generate mood for vote buttons
            mood = 'neutral'
            try:
                from .virality import generate_insight
                insight = generate_insight(alert)
                mood = insight.get('mood', 'neutral')
            except Exception:
                pass
            buttons = build_share_buttons(message, mood=mood, txid_short=txid_short)
            result = send_to_all_channels(message, photo_path=photo_path, inline_buttons=buttons)
            sent_count += result['success']

        send_admin_reply(chat_id,
            f"✅  TEST complete: {len(alerts)} alert(s) generated, {sent_count} sent.\n\n"
            f"Check your channels — you should see beautiful alert cards NOW.\n"
            f"These are REAL latest transactions (clearly marked as TEST).")
    except Exception as e:
        log.exception(f"Test mode error: {e}")
        send_admin_reply(chat_id, f"❌  Test mode error: {e}")


# =====================================================================
# PERSONALIZATION FLOW — the viral mechanic
# =====================================================================
def _handle_start(chat_id: str, user_id: str, username: str) -> None:
    """Handle plain /start — welcome message + show what the bot does."""
    is_adm = is_admin(user_id)
    divider = "━" * 30
    msg = (
        f"🐋  Welcome to OnchainPulse Whale Alert Bot!\n"
        f"{divider}\n\n"
        f"This bot posts real-time whale alerts to Telegram channels.\n\n"
        f"✨  WHAT MAKES OUR ALERTS SPECIAL:\n"
        f"  • Beautiful royal-themed shareable cards\n"
        f"  • Direction analysis (→ sell, ← buy signals)\n"
        f"  • Whale Score (0-100) for instant significance\n"
        f"  • Cluster detection (4+ whales in 30 min)\n"
        f"  • Whale of the Week announcement\n\n"
        f"🎨  PERSONALIZE & SHARE:\n"
        f"  When you see an alert in a channel, tap 'Personalize & Share'\n"
        f"  to get your OWN version of the card with your name on it!\n"
        f"  Then share it on Twitter, Telegram, anywhere — it's yours.\n\n"
    )
    if is_adm:
        msg += "🛡  You are an ADMIN. Send /help to see admin commands.\n\n"
    msg += "📡 Daily charts: @OnchainPulse3\n"
    msg += "🛠 40+ crypto tools — try free: @Onchainpulse1_bot"
    send_admin_reply(chat_id, msg)


def _handle_spot_request(chat_id: str, user_id: str, txid_short: str) -> None:
    """User tapped 'Personalize & Share' on an alert.
    Look up the alert metadata and ask for their username."""
    if not txid_short:
        send_admin_reply(chat_id,
            "❌  Invalid alert link.\n\n"
            "Tap 'Personalize & Share' button on a whale alert to get your personalized card.")
        return

    # Look up alert metadata
    meta = get_alert_meta(txid_short)
    if not meta:
        send_admin_reply(chat_id,
            f"❌  This alert is no longer available for personalization.\n\n"
            f"We keep the last 500 alerts for personalization. This one has expired.\n\n"
            f"🎯  Watch for new alerts in the channel and tap 'Personalize & Share' quickly!\n\n"
            f"📡 Daily charts: @OnchainPulse3\n"
            f"🛠 40+ crypto tools — try free: @Onchainpulse1_bot")
        return

    # Store pending personalization
    set_pending_personalization(user_id, txid_short)

    # Ask for username
    value_usd = meta.get('value_usd', 0)
    asset = meta.get('asset', '?')
    if value_usd >= 1_000_000:
        val_str = f"${value_usd/1_000_000:.1f}M"
    else:
        val_str = f"${value_usd:,.0f}"

    divider = "━" * 30
    send_admin_reply(chat_id,
        f"🎨  PERSONALIZE YOUR WHALE CARD\n"
        f"{divider}\n\n"
        f"Alert: {val_str} {asset}\n\n"
        f"I'll create a beautiful personalized version of this card with YOUR name on it.\n\n"
        f"👤  What name or @username should I put on the card?\n\n"
        f"  • Send your Telegram @username (e.g. @satoshi)\n"
        f"  • Or any name/nickname you want\n"
        f"  • Max 20 characters\n\n"
        f"The card will say: '👁 SPOTTED BY @yourname'\n\n"
        f"Then you can share it on Twitter, Telegram, anywhere — it's YOUR card.")


def _handle_personalization_response(chat_id: str, user_id: str,
                                       username_text: str, pending: dict) -> None:
    """User sent their username after /spot request. Generate personalized card.
    Sends immediate 'please wait' message, then generates card."""
    try:
        # Sanitize username
        username = username_text.strip().lstrip('@').replace('\n', ' ').replace('\r', '')[:20]
        # Remove any non-printable chars
        username = ''.join(c for c in username if c.isprintable() and c not in '<>&"\'\\')

        if not username or len(username) < 2:
            send_admin_reply(chat_id,
                "❌  Please send a valid name (2-20 characters).\n\n"
                "Try again — send your @username or a nickname.")
            return

        txid_short = pending.get('txid_short', '')
        meta = get_alert_meta(txid_short)
        if not meta:
            send_admin_reply(chat_id,
                "❌  This alert has expired. Please tap 'Personalize & Share' on a fresh alert.")
            clear_pending_personalization(user_id)
            return

        # Clear pending state
        clear_pending_personalization(user_id)

        # IMMEDIATE "please wait" message — so user knows bot received their request
        # and is processing. This is sent BEFORE card generation.
        send_admin_reply(chat_id,
            f"⏳  Got it! Generating your personalized card for @{username}...\n\n"
            f"This takes a few seconds. Your card will appear here shortly.\n"
            f"(Bot polls every minute during peak hours)")

        # Generate personalized card
        from .card_generator import generate_alert_card
        from .formatter import format_alert

        photo_path = generate_alert_card(meta, username=username)

        if not photo_path:
            # Fallback: send text only
            msg = format_alert(meta)
            send_admin_reply(chat_id,
                f"✅  Your personalized alert (text only — image generation failed):\n\n{msg}")
            return

        # Build the caption
        value_usd = meta.get('value_usd', 0)
        asset = meta.get('asset', '?')
        if value_usd >= 1_000_000:
            val_str = f"${value_usd/1_000_000:.1f}M"
        else:
            val_str = f"${value_usd:,.0f}"

        dir_label = meta.get('direction', {}).get('label', '')
        score = meta.get('score', 0)

        divider = "━" * 30
        caption = (
            f"✨  YOUR PERSONALIZED WHALE CARD\n"
            f"{divider}\n\n"
            f"🎨  Spotted by @{username}\n"
            f"🐋  {val_str} {asset} whale move\n"
            f"{dir_label}\n"
            f"Whale Score: {score}/100\n\n"
            f"📸  Save this card and share it anywhere:\n"
            f"  • Twitter / X — tap the button below\n"
            f"  • Telegram chats — tap 'Forward'\n"
            f"  • Instagram, Discord, anywhere\n\n"
            f"{divider}\n"
            f"📡 Daily charts: @OnchainPulse3\n"
            f"🛠 40+ crypto tools — try free: @Onchainpulse1_bot"
        )[:1024]  # Telegram caption limit

        # Build share buttons
        tweet_url = build_twitter_intent_url(meta, username=username)
        alert_text = format_alert(meta)
        buttons = build_personalized_card_buttons(
            tweet_url=tweet_url,
            alert_text=alert_text,
        )

        # Send photo with caption + buttons via Telegram API
        import os
        import requests
        from .config import TELEGRAM_BOT_TOKEN, TG_SEND_TIMEOUT
        import json

        if not TELEGRAM_BOT_TOKEN or not os.path.exists(photo_path):
            send_admin_reply(chat_id, "❌  Could not generate card. Please try again.")
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            with open(photo_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': chat_id,
                    'caption': caption,
                }
                if buttons:
                    data['reply_markup'] = json.dumps({'inline_keyboard': buttons})
                resp = requests.post(url, files=files, data=data, timeout=TG_SEND_TIMEOUT + 30)

            if resp.status_code == 200 and resp.json().get('ok'):
                log.info(f"Personalized card sent to user {user_id} for txid {txid_short}")
            else:
                log.error(f"Failed to send personalized card: {resp.text[:200]}")
                send_admin_reply(chat_id,
                    "❌  Could not send the card image. Please try again with a fresh alert.")
        except Exception as e:
            log.error(f"sendPhoto error: {e}")
            send_admin_reply(chat_id,
                f"❌  Error sending card: {e}. Please try again with a fresh alert.")

    except Exception as e:
        log.exception(f"Personalization response error: {e}")
        try:
            clear_pending_personalization(user_id)
        except Exception:
            pass
        send_admin_reply(chat_id, f"❌  Error generating card: {e}. Please try again.")


# =====================================================================
# MAIN POLLING LOOP
# =====================================================================
def main():
    """Poll Telegram for admin commands. Run every 5 minutes via GitHub Actions."""
    log.info("=" * 60)
    log.info("ADMIN BOT - polling for commands")
    log.info(f"Super-admins from env: {SUPER_ADMIN_IDS or '(none)'}")
    log.info("=" * 60)

    offset = get_update_offset()
    # Get all pending updates (long poll with timeout 0 = quick)
    updates = get_updates(offset=offset, timeout=0)

    if not updates:
        log.info("No new updates")
        return 0

    log.info(f"Processing {len(updates)} update(s)")
    max_update_id = offset

    for update in updates:
        update_id = update.get('update_id', 0)
        if update_id >= max_update_id:
            max_update_id = update_id + 1
        try:
            handle_command(update)
        except Exception as e:
            log.exception(f"Update handling failed: {e}")
        # Small delay between commands
        time.sleep(0.3)

    # Save offset
    set_update_offset(max_update_id)
    log.info(f"Done. Next offset: {max_update_id}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
