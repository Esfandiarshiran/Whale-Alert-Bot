"""
Main entry point for whale scan workflow.
Run: python -m src.main

Logic:
1. First run ever -> post welcome message to all channels
2. Every run -> scan for large txs, post new ones
3. Every 24h -> post daily summary (even if no alerts)
4. Every run -> cleanup old card PNGs (disk hygiene)
"""
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from .analyzer import run_whale_scan
from .telegram import send_to_all_channels, build_share_buttons
from .cache import (
    is_posted, mark_posted, is_first_run, mark_initialized,
     get_stats, reset_stats, diagnostics,
    should_post_weekly_winner, get_weekly_winner, get_weekly_state,
    mark_weekly_winner_posted,
)
from .supabase import get_channel_count
from .config import FOOTER_TEXT, CARDS_DIR, log
from .formatter import (
    format_welcome_message, format_status_message,
    format_weekly_winner,
)
from .card_generator import  generate_weekly_winner_card


def cleanup_old_cards(max_age_hours: int = 24) -> int:
    """Delete card PNGs older than max_age_hours. Prevents disk bloat.
    CRITICAL: never raises — wraps everything in try/except.
    Called AFTER all sends complete, so we never delete a card mid-send."""
    deleted = 0
    try:
        if not CARDS_DIR.exists():
            return 0
        now = datetime.now(timezone.utc).timestamp()
        for f in CARDS_DIR.glob('*.png'):
            try:
                mtime = f.stat().st_mtime
                age_hours = (now - mtime) / 3600
                if age_hours > max_age_hours:
                    f.unlink()
                    deleted += 1
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Card cleanup error: {e}")
    return deleted


def _alert_admin_critical(error_msg: str) -> None:
    """Send critical error alert to super-admins via Telegram.
    Only for truly critical errors (Supabase down, all channels failed, etc.)."""
    try:
        from .config import SUPER_ADMIN_IDS, TELEGRAM_BOT_TOKEN
        import requests
        if not TELEGRAM_BOT_TOKEN or not SUPER_ADMIN_IDS:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        divider = "━" * 25
        msg = (
            f"🚨 CRITICAL ERROR\n"
            f"{divider}\n"
            f"{error_msg[:500]}\n\n"
            f"Bot will retry next scheduled run."
        )
        for admin_id in SUPER_ADMIN_IDS:
            try:
                requests.post(url, data={
                    'chat_id': admin_id,
                    'text': msg,
                    'disable_web_page_preview': True,
                }, timeout=10)
            except Exception:
                pass
    except Exception:
        pass  # Never let alerting crash the bot


def main():
    log.info("=" * 60)
    log.info("WHALE ALERT BOT v2.1 - Starting scan")
    log.info(f"Channels configured: {get_channel_count()}")
    log.info("=" * 60)

    # === Step 1: First-run welcome ===
    first_run = is_first_run()
    if first_run:
        log.info("First run detected - posting welcome message")
        welcome = format_welcome_message()
        result = send_to_all_channels(welcome)
        if result['success'] > 0:
            mark_initialized()
            log.info(f"Welcome sent to {result['success']} channel(s)")
        else:
            log.error("Failed to send welcome - will retry next run")
            _alert_admin_critical(
                "Failed to send welcome message to ANY channel.\n"
                "Possible causes: Supabase not configured, bot not admin in channel, "
                "or Telegram API issues."
            )
            return 1
        time.sleep(2)
    else:
        log.info("Not first run - proceeding to scan")

    # === Step 2: Scan ===
    try:
        alerts = run_whale_scan()
    except Exception as e:
        log.exception(f"Scan failed: {e}")
        _alert_admin_critical(f"Scan failed with error:\n{e}")
        alerts = []

    # === Step 3: Post alerts ===
    posted = 0
    for message, photo_path, tx_id, alert_type, meta in alerts:
        # Build share buttons (only for individual alerts, not cluster)
        buttons = None
        if alert_type != 'cluster':
            # Simple: just Share on Twitter button
            buttons = build_share_buttons(message)

        if send_to_all_channels(message, photo_path=photo_path, inline_buttons=buttons)['success'] > 0:
            mark_posted(tx_id, alert_type)
            posted += 1
        else:
            log.warning(f"Failed to send alert {tx_id} to any channel")

    log.info(f"Posted {posted} new alerts")

    # # === Step 4: Daily summary ===
    # if should_post_summary(hours=24):
    #     log.info("Time for daily summary")
    #     stats = get_stats()
    #     today_flow = get_today_flow()

    #     # Build summary stats
    #     summary_stats = {
    #         'total_alerts': stats.get('total', 0),
    #         'btc_count': stats.get('btc', 0),
    #         'eth_count': stats.get('eth', 0),
    #         'stable_count': stats.get('stable', 0) + stats.get('token', 0),
    #         'total_usd': today_flow.get('exchange_in', 0) + today_flow.get('exchange_out', 0) + today_flow.get('inter_wallet', 0),
    #         'net_flow': today_flow.get('exchange_in', 0) - today_flow.get('exchange_out', 0),
    #         'top_whale': None,
    #     }

    #     summary_msg = format_daily_summary(summary_stats)
    #     summary_card = generate_summary_card(summary_stats)

    #     send_result = send_to_all_channels(summary_msg, photo_path=summary_card)
    #     if send_result['success'] > 0:
    #         mark_summary_posted()
    #         reset_stats()
    #         log.info(f"Daily summary posted to {send_result['success']} channel(s)")
    #     else:
    #         log.warning("Failed to post daily summary (no channels or all failed)")
    #     time.sleep(1)

    # === Step 5: Weekly Whale of the Week ===
    if should_post_weekly_winner():
        log.info("Time for weekly Whale of the Week announcement")
        winner = get_weekly_winner()
        if winner:
            weekly_state = get_weekly_state()
            runner_ups = weekly_state.get('candidates', [])[1:5]  # next 4 after winner
            try:
                weekly_msg = format_weekly_winner(winner, runner_ups)
                weekly_card = generate_weekly_winner_card(winner, runner_ups)
                send_result = send_to_all_channels(weekly_msg, photo_path=weekly_card)
                if send_result['success'] > 0:
                    mark_weekly_winner_posted(winner)
                    log.info(f"Weekly winner posted to {send_result['success']} channel(s): ${winner.get('value_usd', 0):,.0f} {winner.get('asset','?')}")
                else:
                    log.warning("Failed to post weekly winner (no channels or all failed)")
            except Exception as e:
                log.warning(f"Weekly winner error: {e}")
        else:
            log.info("No weekly candidates yet — skipping winner post")
        time.sleep(1)

    # === Step 6: Cleanup old cards (AFTER all sends complete) ===
    # Cards older than 24h are safe to delete — sends are complete by now
    deleted = cleanup_old_cards(max_age_hours=24)
    if deleted:
        log.info(f"Cleanup: removed {deleted} old card(s)")

    # === Step 7: Diagnostics ===
    diag = diagnostics()
    log.info(f"Diagnostics: wallets={diag['wallets_tracked']} alerts_in_mem={diag['recent_alerts_count']}")
    log.info("Done")
    return 0


if __name__ == '__main__':
    sys.exit(main())
