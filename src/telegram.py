"""
Telegram sender for whale alerts.
- Sends to ALL active channels from Supabase (multi-channel distribution)
- Sends text + optional PNG card as photo (high engagement)
- Per-channel error isolation: failure on one channel doesn't affect others
- Automatic removal of failed channels (after 5 consecutive failures)
- Inline share button for virality

CRITICAL: NEVER raises. All errors are caught and logged.
The bot must NEVER crash due to a Telegram send failure.
"""
import time
import os
import json
import requests
from typing import List, Dict, Optional, Tuple
from .config import (
    TELEGRAM_BOT_TOKEN, TG_SEND_DELAY_SEC, TG_SEND_TIMEOUT,
    TG_MAX_RETRIES, FOOTER_MAIN_BOT, log,
)
from .http import fetch_json, post_json
from . import supabase as supa


# =====================================================================
# CHANNEL FAILURE TRACKER (in-process)
# =====================================================================
_channel_failures: Dict[str, int] = {}  # channel_id -> consecutive failure count
_FAILURE_THRESHOLD = 5  # after this many consecutive failures, disable channel


def _record_failure(channel_id: str) -> None:
    _channel_failures[channel_id] = _channel_failures.get(channel_id, 0) + 1
    if _channel_failures[channel_id] >= _FAILURE_THRESHOLD:
        log.error(f"Channel {channel_id} failed {_channel_failures[channel_id]} times - auto-disabling")
        try:
            supa.remove_channel(channel_id)
        except Exception as e:
            log.warning(f"Could not auto-disable channel: {e}")


def _record_success(channel_id: str) -> None:
    _channel_failures[channel_id] = 0


# =====================================================================
# SEND TO ALL CHANNELS
# =====================================================================
def send_to_all_channels(message: str, photo_path: str = None,
                          inline_buttons: List[List[Dict]] = None,
                          disable_preview: bool = True) -> Dict:
    """
    Send a message (with optional photo) to ALL active channels.
    Returns: {success: int, failed: int, channels: [...]}
    """
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set - skipping send")
        return {'success': 0, 'failed': 0, 'channels': []}

    channels = supa.list_channels(active_only=True)
    if not channels:
        log.warning("No active channels configured")
        return {'success': 0, 'failed': 0, 'channels': []}

    log.info(f"Sending to {len(channels)} channel(s)")

    success = 0
    failed = 0
    channel_results = []

    for ch in channels:
        channel_id = ch.get('channel_id') or ch.get('channel_username')
        if not channel_id:
            log.warning(f"Skipping channel with no ID: {ch}")
            continue

        ok = _send_to_one_channel(channel_id, message, photo_path, inline_buttons, disable_preview)
        channel_results.append({
            'channel': channel_id,
            'success': ok,
        })
        if ok:
            success += 1
            _record_success(channel_id)
        else:
            failed += 1
            _record_failure(channel_id)
        # Rate limit between channels
        time.sleep(TG_SEND_DELAY_SEC)

    log.info(f"Send complete: {success} ok, {failed} failed")
    return {'success': success, 'failed': failed, 'channels': channel_results}


def _send_to_one_channel(channel_id: str, message: str, photo_path: str = None,
                          inline_buttons: List[List[Dict]] = None,
                          disable_preview: bool = True) -> bool:
    """
    Send to a single channel. Returns True on success, False on failure.
    Tries photo first if photo_path is provided, falls back to text-only.
    """
    # If we have a photo, use sendPhoto
    if photo_path and os.path.exists(photo_path):
        if _send_photo(channel_id, photo_path, message, inline_buttons):
            return True
        # Fall back to text-only
        log.info(f"Photo send failed for {channel_id}, falling back to text-only")

    return _send_text(channel_id, message, inline_buttons, disable_preview)


def _send_text(channel_id: str, message: str,
               inline_buttons: List[List[Dict]] = None,
               disable_preview: bool = True) -> bool:
    """Send plain text. No parse_mode to avoid HTML/Markdown errors."""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': channel_id,
        'text': message,
        'disable_web_page_preview': disable_preview,
    }
    if inline_buttons:
        data['reply_markup'] = json.dumps({'inline_keyboard': inline_buttons})

    for attempt in range(TG_MAX_RETRIES):
        try:
            resp = requests.post(url, data=data, timeout=TG_SEND_TIMEOUT)
            rjson = {}
            try:
                rjson = resp.json()
            except Exception:
                pass
            if resp.status_code == 200 and rjson.get('ok'):
                log.debug(f"Text sent to {channel_id}")
                return True

            # 400 = bad request (e.g. chat not found, bot not admin)
            # 403 = forbidden (e.g. kicked from channel)
            if resp.status_code in (400, 403):
                desc = rjson.get('description', '')
                log.error(f"Telegram {resp.status_code} for {channel_id}: {desc}")
                return False  # don't retry - won't fix itself

            # 429 = rate limited
            if resp.status_code == 429:
                retry_after = rjson.get('parameters', {}).get('retry_after', 2)
                log.warning(f"Rate limited, waiting {retry_after}s")
                time.sleep(retry_after + 1)
                continue

            # 5xx - retry
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue

            log.error(f"Telegram send failed {resp.status_code}: {rjson}")
            return False

        except requests.exceptions.Timeout:
            log.warning(f"Timeout sending to {channel_id} (try {attempt+1})")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            log.warning(f"Network error sending to {channel_id} (try {attempt+1}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.warning(f"Unexpected error sending to {channel_id}: {e}")
            return False

    return False


def _send_photo(channel_id: str, photo_path: str, caption: str,
                inline_buttons: List[List[Dict]] = None) -> bool:
    """Send a photo with caption. Caption limit is 1024 chars.
    Re-opens file on each retry to avoid handle leaks."""
    if not os.path.exists(photo_path):
        return False

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
    # Truncate caption to 1024 chars (Telegram limit)
    caption = (caption or '')[:1024]
    buttons_json = json.dumps({'inline_keyboard': inline_buttons}) if inline_buttons else None

    for attempt in range(TG_MAX_RETRIES):
        try:
            with open(photo_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': channel_id,
                    'caption': caption,
                }
                if buttons_json:
                    data['reply_markup'] = buttons_json

                resp = requests.post(url, files=files, data=data, timeout=TG_SEND_TIMEOUT + 30)

            rjson = {}
            try:
                rjson = resp.json()
            except Exception:
                pass
            if resp.status_code == 200 and rjson.get('ok'):
                log.debug(f"Photo sent to {channel_id}")
                return True
            if resp.status_code in (400, 403):
                log.error(f"Telegram photo {resp.status_code} for {channel_id}: {rjson.get('description','')}")
                return False
            if resp.status_code == 429:
                retry_after = rjson.get('parameters', {}).get('retry_after', 2)
                log.warning(f"Photo rate limited, waiting {retry_after}s")
                time.sleep(retry_after + 1)
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return False
        except requests.exceptions.RequestException as e:
            log.warning(f"Photo send network error (try {attempt+1}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.warning(f"Photo send error: {e}")
            return False
    return False


# =====================================================================
# INLINE BUTTONS (for virality + interactivity)
# =====================================================================
def build_share_buttons(tx_text: str = None, mood: str = None,
                         txid_short: str = None) -> List[List[Dict]]:
    """
    Build inline keyboard for CHANNEL posts.
    IMPORTANT: In Telegram channels, switch_inline_query buttons are unreliable.
    Only URL buttons work reliably for channel subscribers.
    So we use URL buttons only:
    1. PERSONALIZE (url → deep link to bot DM)
    2. SHARE ON TWITTER (url → twitter intent)
    3. Cross-promo: "🛠 40+ crypto tools" (url)

    The personalization button is the KEY viral mechanic — it opens a DM
    with the bot where switch_inline_query buttons DO work.
    """
    from .config import TELEGRAM_BOT_USERNAME
    from urllib.parse import quote

    buttons = []

    # === Row 1: PERSONALIZE & SHARE (the viral mechanic) ===
    if TELEGRAM_BOT_USERNAME and txid_short:
        deep_link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start=spot_{txid_short}"
        buttons.append([{
            'text': '🎨  Personalize & Share this card',
            'url': deep_link,
        }])

    # === Row 2: Share on Twitter (URL button — works in channels) ===
    # Build a short tweet intent
    if tx_text:
        # Extract key info for tweet (first 200 chars)
        tweet_text = tx_text[:200]
        if len(tx_text) > 200:
            tweet_text += '...'
        tweet_url = f"https://twitter.com/intent/tweet?text={quote(tweet_text)}"
        buttons.append([{
            'text': '🐦  Share on Twitter / X',
            'url': tweet_url,
        }])

    # === Row 3: Cross-promo (the funnel) ===
    buttons.append([{
        'text': '🛠  40+ crypto tools — try free',
        'url': f'https://t.me/{FOOTER_MAIN_BOT.lstrip("@")}',
    }])
    return buttons


def build_personalized_card_buttons(tweet_url: str = None, alert_text: str = None) -> List[List[Dict]]:
    """
    Build buttons for the personalized card delivery (sent to user's DM).
    These are the SHARE buttons — one-click distribution to social platforms.

    Row 1: "🐦 Tweet this" (URL to twitter intent)
    Row 2: "📢 Forward on Telegram" + "📱 Post to my channel"
    Row 3: "🔄 Make another" (back to /spot)
    Row 4: Cross-promo (the funnel)
    """
    from .config import TELEGRAM_BOT_USERNAME
    buttons = []

    # Row 1: Twitter share
    if tweet_url:
        buttons.append([{
            'text': '🐦  Share on Twitter / X',
            'url': tweet_url,
        }])

    # Row 2: Telegram forward + post to channel
    if alert_text:
        # switch_inline_query lets user pick any chat to forward to
        share_text = (alert_text[:256] + '...') if len(alert_text) > 256 else alert_text
        buttons.append([
            {
                'text': '📢  Forward to chats',
                'switch_inline_query': share_text,
            },
            {
                'text': '📱  Post to my channel',
                'switch_inline_query': share_text,
            },
        ])

    # Row 3: Make another
    if TELEGRAM_BOT_USERNAME:
        buttons.append([{
            'text': '🔄  Personalize another alert',
            'url': f'https://t.me/{TELEGRAM_BOT_USERNAME}?start=help',
        }])

    # Row 4: Cross-promo
    buttons.append([{
        'text': '🛠  40+ crypto tools — try free',
        'url': f'https://t.me/{FOOTER_MAIN_BOT.lstrip("@")}',
    }])

    return buttons


def build_twitter_intent_url(alert: dict, username: str = None) -> str:
    """
    Build a Twitter intent URL with pre-filled tweet text.
    User still needs to attach the card image manually (Twitter API limitation).
    """
    from urllib.parse import quote
    value_usd = alert.get('value_usd', 0)
    asset = alert.get('asset', 'BTC')
    if value_usd >= 1_000_000:
        val_str = f"${value_usd/1_000_000:.1f}M"
    else:
        val_str = f"${value_usd:,.0f}"

    dir_label = alert.get('direction', {}).get('label', '')
    score = alert.get('score', 0)

    if username:
        spotted = f"Spotted by @{username}  "
    else:
        spotted = ""

    tweet_text = (
        f"🐋 {val_str} {asset} whale move just detected!\n"
        f"{dir_label}\n"
        f"Whale Score: {score}/100\n\n"
        f"{spotted}"
        f"Get real-time whale alerts: t.me/onnchainWhaleAlert\n"
        f"#Bitcoin #CryptoWhales #OnChain"
    )
    return f"https://twitter.com/intent/tweet?text={quote(tweet_text)}"


# =====================================================================
# ADMIN COMMAND POLLING
# =====================================================================
def get_updates(offset: int = 0, timeout: int = 0) -> List[Dict]:
    """Poll Telegram for new updates (admin commands).
    Returns list of update dicts. NEVER raises."""
    if not TELEGRAM_BOT_TOKEN:
        return []
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
    params = {
        'offset': offset,
        'timeout': timeout,
        'allowed_updates': json.dumps(['message']),
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout + 10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('result', [])
        log.warning(f"getUpdates returned {resp.status_code}: {resp.text[:200]}")
        return []
    except Exception as e:
        log.warning(f"getUpdates error: {e}")
        return []


def send_admin_reply(chat_id: str, text: str) -> bool:
    """Send a reply to an admin's command. Never raises."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text,
        'disable_web_page_preview': True,
    }
    try:
        resp = requests.post(url, data=data, timeout=TG_SEND_TIMEOUT)
        return resp.status_code == 200
    except Exception as e:
        log.warning(f"Admin reply error: {e}")
        return False
