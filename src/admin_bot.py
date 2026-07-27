"""
Admin command processor — SIMPLE VERSION (no personalization).

Handles:
- /start — welcome message
- /help — show commands
- /status — bot status
- /stats — today's stats
- /addchannel, /removechannel, /listchannels — admin channel management
- /addadmin, /removeadmin, /listadmins — admin user management
- /test [btc|eth|tron] — generate ONE sample alert

CRITICAL: Only super-admins (env) and admins (Supabase) can run privileged commands.
Security: never trust user input - validate all arguments.
"""
import sys
import time
import json
from .telegram import get_updates, send_admin_reply, build_share_buttons
from .cache import get_update_offset, set_update_offset, get_stats, diagnostics
from .supabase import (
    list_channels, add_channel, remove_channel, get_channel_count,
    is_admin, list_admins, add_admin, remove_admin,
)
from .config import (
    SUPER_ADMIN_IDS, FOOTER_TEXT, FOOTER_MAIN_BOT, FOOTER_MAIN_CHANNEL,
    ADMIN_CMD_MAX_PER_USER, ADMIN_CMD_MAX_PER_RUN, log,
)
from .formatter import format_help_message, format_status_message


# Commands that require admin
ADMIN_COMMANDS = {'/addchannel', '/removechannel', '/listchannels',
                  '/addadmin', '/removeadmin', '/listadmins', '/test'}

# Rate limiting state (per polling session)
_user_command_counts = {}  # user_id -> count
_total_commands = 0


def handle_command(update: dict) -> None:
    """Process a single Telegram update (message).
    Includes rate limiting to prevent abuse."""
    global _total_commands
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

        # SECURITY: Limit message length to prevent abuse
        if len(text) > 1000:
            log.warning(f"Message too long ({len(text)} chars) from user, ignoring")
            return

        user = message.get('from') or {}
        user_id = str(user.get('id', ''))
        username = user.get('username', '') or user.get('first_name', '')

        # RATE LIMITING: per-user limit
        user_count = _user_command_counts.get(user_id, 0)
        if user_count >= ADMIN_CMD_MAX_PER_USER:
            log.warning(f"User {user_id} hit rate limit ({user_count} commands)")
            # Only warn once per session
            if user_count == ADMIN_CMD_MAX_PER_USER:
                send_admin_reply(chat_id, "⚠️ Rate limit reached. Please wait for next polling cycle.")
            _user_command_counts[user_id] = user_count + 1
            return

        # RATE LIMITING: total commands per run
        if _total_commands >= ADMIN_CMD_MAX_PER_RUN:
            log.warning(f"Total command limit reached ({_total_commands}), skipping")
            return

        _user_command_counts[user_id] = user_count + 1
        _total_commands += 1

        # Parse command + args
        parts = text.split()
        if not parts:
            return
        cmd = parts[0].lower().split('@')[0]  # strip bot mention
        args = parts[1:]

        log.info(f"Command from {user_id} ({username}): {cmd} {args[:2]}")

        # === Public commands ===
        if cmd == '/start':
            _handle_start(chat_id, user_id, username)
            return

        if cmd == '/help':
            send_admin_reply(chat_id, format_help_message(is_admin=is_admin(user_id)))
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
                f"📊 TODAY'S WHALE STATS\n"
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

        # === Admin-only commands ===
        if cmd in ADMIN_COMMANDS:
            if not is_admin(user_id):
                send_admin_reply(chat_id, "⛔ Access denied. You are not an admin.")
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
            send_admin_reply(chat_id, "⚠️ Internal error processing command.")
        except Exception:
            pass


# =====================================================================
# HANDLERS
# =====================================================================
def _handle_start(chat_id: str, user_id: str, username: str) -> None:
    """Handle plain /start — welcome message."""
    is_adm = is_admin(user_id)
    divider = "━" * 30
    msg = (
        f"🐋 Welcome to OnchainPulse Whale Alert Bot!\n"
        f"{divider}\n\n"
        f"This bot posts real-time whale alerts to Telegram channels.\n\n"
        f"✨ WHAT MAKES OUR ALERTS SPECIAL:\n"
        f"   • Beautiful shareable cards\n"
        f"   • Direction analysis (→ sell, ← buy)\n"
        f"   • Whale Score (0-100)\n"
        f"   • Cluster detection (4+ whales in 30 min)\n"
        f"   • Whale of the Week announcement\n\n"
    )
    if is_adm:
        msg += "🛡 You are an ADMIN. Send /help to see admin commands.\n\n"
    msg += f"📡 Daily charts: @OnchainPulse3\n"
    msg += f"🛠 40+ crypto tools — try free: @Onchainpulse1_bot"
    send_admin_reply(chat_id, msg)


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
            f"✅ Channel added: {channel}\n"
            f"Total channels: {get_channel_count()}\n\n"
            f"⚠️ Make sure the bot is ADMIN in that channel.")
    else:
        send_admin_reply(chat_id, f"❌ Failed: {result.get('error', 'unknown error')}")


def _cmd_remove_channel(chat_id: str, args: list, removed_by: str) -> None:
    if not args:
        send_admin_reply(chat_id, "Usage: /removechannel @username  OR  /removechannel -1001234567890")
        return
    channel = args[0]
    result = remove_channel(channel)
    if result.get('ok'):
        send_admin_reply(chat_id, f"✅ Channel removed: {channel}\nTotal channels: {get_channel_count()}")
    else:
        send_admin_reply(chat_id, f"❌ Failed: {result.get('error', 'unknown error')}")


def _cmd_list_channels(chat_id: str) -> None:
    channels = list_channels(active_only=True)
    if not channels:
        send_admin_reply(chat_id, "No active channels.")
        return
    divider = "━" * 30
    msg = f"📋 ACTIVE CHANNELS ({len(channels)})\n{divider}\n"
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
    msg += f"\n{FOOTER_TEXT}"
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
        send_admin_reply(chat_id, f"✅ Admin added: {new_admin_id} ({username})")
    else:
        send_admin_reply(chat_id, f"❌ Failed: {result.get('error')}")


def _cmd_remove_admin(chat_id: str, args: list, removed_by: str) -> None:
    if not args:
        send_admin_reply(chat_id, "Usage: /removeadmin <numeric_user_id>")
        return
    target_id = args[0]
    if target_id in SUPER_ADMIN_IDS:
        send_admin_reply(chat_id, "❌ Cannot remove super-admin from env config.")
        return
    result = remove_admin(target_id)
    if result.get('ok'):
        send_admin_reply(chat_id, f"✅ Admin removed: {target_id}")
    else:
        send_admin_reply(chat_id, f"❌ Failed: {result.get('error')}")


def _cmd_list_admins(chat_id: str) -> None:
    admins = list_admins()
    divider = "━" * 30
    msg = f"👥 ADMINS ({len(admins)})\n{divider}\n"
    for i, a in enumerate(admins, 1):
        uid = a.get('telegram_user_id', '?')
        uname = a.get('username', '') or ''
        is_super = a.get('is_super_admin', False)
        marker = "👑" if is_super else "🛡"
        msg += f"{i}. {marker}  {uid}"
        if uname:
            msg += f"  (@{uname})"
        msg += "\n"
    msg += f"\n{FOOTER_TEXT}"
    send_admin_reply(chat_id, msg)


def _cmd_test(chat_id: str, args: list) -> None:
    """Generate ONE sample alert. Usage: /test [btc|eth|tron]"""
    source = args[0].lower() if args else 'btc'
    if source not in ('btc', 'eth', 'tron'):
        source = 'btc'  # default to BTC instead of 'all'

    send_admin_reply(chat_id,
        f"🧪 Generating ONE test alert from source: {source}\n"
        f"This takes ~30 seconds (fetching real latest tx)...")

    try:
        from .test_mode import build_test_alert_btc, build_test_alert_eth, build_test_alert_tron
        from .formatter import format_alert
        from .card_generator import generate_alert_card
        from .telegram import send_to_all_channels

        # Build ONE alert only (not all sources)
        alert = None
        if source == 'btc':
            alert = build_test_alert_btc()
        elif source == 'eth':
            alert = build_test_alert_eth()
        elif source == 'tron':
            alert = build_test_alert_tron()

        if not alert:
            send_admin_reply(chat_id, "❌ Could not generate test alert (network issues or no recent txs).")
            return

        from .test_mode import TEST_MARKER
        message = format_alert(alert)
        message = f"{TEST_MARKER}\n\n{message}"
        photo_path = generate_alert_card(alert)
        buttons = build_share_buttons(message)
        result = send_to_all_channels(message, photo_path=photo_path, inline_buttons=buttons)

        if result['success'] > 0:
            send_admin_reply(chat_id,
                f"✅ Test alert sent to {result['success']} channel(s).\n\n"
                f"Check your channels — you should see a beautiful alert card NOW.\n"
                f"This is a REAL latest transaction (clearly marked as TEST).")
        else:
            send_admin_reply(chat_id,
                f"❌ Failed to send test alert.\n"
                f"Check: bot is admin in channel? Supabase configured?")

    except Exception as e:
        log.exception(f"Test mode error: {e}")
        send_admin_reply(chat_id, f"❌ Test mode error: {e}")


# =====================================================================
# MAIN POLLING LOOP
# =====================================================================
def main():
    """Poll Telegram for admin commands."""
    log.info("=" * 60)
    log.info("ADMIN BOT - polling for commands")
    log.info(f"Super-admins from env: {SUPER_ADMIN_IDS or '(none)'}")
    log.info("=" * 60)

    offset = get_update_offset()
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
        time.sleep(0.3)

    set_update_offset(max_update_id)
    log.info(f"Done. Next offset: {max_update_id}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
