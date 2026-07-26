"""
Supabase client for multi-channel management.

Tables (defined in scripts/setup_supabase.sql):
  - WhaleAlert (channels) — with marketing analytics columns
  - whale_admins (admin users)
  - whale_clicks (per-channel click tracking for the funnel)

CRITICAL: Never raises. On any DB error, returns empty results.
The bot REQUIRES Supabase to be configured (no env-channel fallback anymore,
since we want all channels managed in DB for clean analytics).
"""
import os
import requests
from datetime import datetime, timezone
from typing import List, Optional, Dict
from .config import SUPABASE_URL, SUPABASE_KEY, SUPER_ADMIN_IDS, log
from .http import post_json, fetch_json


# =====================================================================
# Configuration check
# =====================================================================
def _headers() -> dict:
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }


def _is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def is_ready() -> bool:
    """Public check — bot will skip sending if Supabase is not configured."""
    return _is_configured()


# =====================================================================
# CHANNEL CRUD
# =====================================================================
def list_channels(active_only: bool = True) -> List[Dict]:
    """
    Returns list of channel dicts:
      {
        channel_id, channel_username, channel_title,
        added_at, added_by, is_active, notes,
        clicks_count, subscribers_converted, last_click_at
      }
    Returns [] if Supabase is not configured (NO env fallback anymore).
    """
    if not _is_configured():
        log.error("Supabase not configured - cannot list channels")
        return []

    url = f"{SUPABASE_URL}/rest/v1/WhaleAlert?select=*"
    if active_only:
        url += "&is_active=eq.true"
    url += "&order=added_at.asc"
    try:
        data = fetch_json(url, headers=_headers(), timeout=10)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        log.warning(f"Supabase list_channels failed: {e}")
        return []


def add_channel(channel_id: str, username: str = '', title: str = '',
                added_by: str = '', notes: str = '') -> Dict:
    """Add a new channel. Returns the created record, or {} on failure."""
    if not _is_configured():
        return {'ok': False, 'error': 'Supabase not configured'}

    # Normalize: if username provided without @, add it
    if username and not username.startswith('@'):
        username = '@' + username
    # If channel_id is actually a @username, treat it as username
    if channel_id.startswith('@') and not username:
        username = channel_id
        channel_id = ''  # will be resolved on first send

    payload = {
        'channel_id': channel_id,
        'channel_username': username,
        'channel_title': title,
        'added_by': added_by,
        'is_active': True,
        'notes': notes,
        'clicks_count': 0,
        'subscribers_converted': 0,
    }
    try:
        url = f"{SUPABASE_URL}/rest/v1/WhaleAlert"
        resp = post_json(url, data=payload, headers=_headers(), timeout=10)
        if isinstance(resp, list) and resp:
            return {'ok': True, 'channel': resp[0]}
        if isinstance(resp, dict) and resp.get('code'):
            # PostgREST error
            return {'ok': False, 'error': resp.get('message', 'DB error')}
        return {'ok': True, 'channel': payload}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def remove_channel(identifier: str) -> Dict:
    """Soft-delete a channel by id OR username. Sets is_active=False."""
    if not _is_configured():
        return {'ok': False, 'error': 'Supabase not configured'}

    if identifier.startswith('@'):
        url = f"{SUPABASE_URL}/rest/v1/WhaleAlert?channel_username=eq.{identifier}&is_active=eq.true"
    else:
        url = f"{SUPABASE_URL}/rest/v1/WhaleAlert?channel_id=eq.{identifier}&is_active=eq.true"

    try:
        headers = _headers()
        headers['Prefer'] = 'return=representation'
        resp = requests.patch(url, headers=headers, json={'is_active': False}, timeout=10)
        if resp.status_code in (200, 204):
            return {'ok': True, 'removed': identifier}
        return {'ok': False, 'error': f'HTTP {resp.status_code}: {resp.text[:200]}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def get_channel_count() -> int:
    """Count of active channels."""
    if not _is_configured():
        return 0
    try:
        url = f"{SUPABASE_URL}/rest/v1/WhaleAlert?is_active=eq.true&select=channel_id"
        data = fetch_json(url, headers=_headers(), timeout=10)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


# =====================================================================
# ANALYTICS — track clicks & conversions per channel
# (These are populated by your main bot's referral tracking, not by this bot.
#  The columns exist here so when you query WhaleAlert, you see the funnel data.)
# =====================================================================
def get_channel_analytics() -> List[Dict]:
    """
    Returns analytics summary for all channels (including inactive).
    Each row:
      {
        channel_id, channel_username, channel_title, added_at,
        clicks_count, subscribers_converted, trial_activations,
        paid_conversions, last_click_at, is_active
      }
    """
    if not _is_configured():
        return []
    try:
        url = (f"{SUPABASE_URL}/rest/v1/WhaleAlert"
               "?select=channel_id,channel_username,channel_title,added_at,"
               "clicks_count,subscribers_converted,trial_activations,"
               "paid_conversions,last_click_at,is_active"
               "&order=clicks_count.desc")
        data = fetch_json(url, headers=_headers(), timeout=10)
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"get_channel_analytics failed: {e}")
        return []


def get_top_channels(limit: int = 10) -> List[Dict]:
    """Top channels by clicks_count — for marketing dashboard."""
    if not _is_configured():
        return []
    try:
        url = (f"{SUPABASE_URL}/rest/v1/WhaleAlert"
               f"?select=channel_username,channel_title,clicks_count,subscribers_converted"
               f"&clicks_count=gt.0&is_active=eq.true"
               f"&order=clicks_count.desc&limit={limit}")
        data = fetch_json(url, headers=_headers(), timeout=10)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# =====================================================================
# ADMIN management
# =====================================================================
def is_admin(telegram_user_id: str) -> bool:
    """Check if a user is in the admin list. Super-admins (env) always pass."""
    if not telegram_user_id:
        return False
    if telegram_user_id in SUPER_ADMIN_IDS:
        return True
    if not _is_configured():
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/whale_admins?telegram_user_id=eq.{telegram_user_id}&is_active=eq.true"
        data = fetch_json(url, headers=_headers(), timeout=10)
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


def list_admins() -> List[Dict]:
    if not _is_configured():
        return [{'telegram_user_id': uid, 'is_super_admin': True, 'username': '(super-admin)'} for uid in SUPER_ADMIN_IDS]
    try:
        url = f"{SUPABASE_URL}/rest/v1/whale_admins?select=*&order=added_at.asc"
        data = fetch_json(url, headers=_headers(), timeout=10)
        out = list(data) if isinstance(data, list) else []
        for uid in SUPER_ADMIN_IDS:
            if not any(a.get('telegram_user_id') == uid for a in out):
                out.append({'telegram_user_id': uid, 'is_super_admin': True, 'username': '(super-admin from env)'})
        return out
    except Exception:
        return [{'telegram_user_id': uid, 'is_super_admin': True, 'username': '(super-admin)'} for uid in SUPER_ADMIN_IDS]


def add_admin(telegram_user_id: str, username: str = '', added_by: str = '') -> Dict:
    if not _is_configured():
        return {'ok': False, 'error': 'Supabase not configured'}
    if not telegram_user_id.isdigit():
        return {'ok': False, 'error': 'Telegram user ID must be numeric'}
    payload = {
        'telegram_user_id': telegram_user_id,
        'username': username,
        'added_by': added_by,
        'is_active': True,
        'is_super_admin': False,
    }
    try:
        url = f"{SUPABASE_URL}/rest/v1/whale_admins"
        resp = post_json(url, data=payload, headers=_headers(), timeout=10)
        if isinstance(resp, list):
            return {'ok': True, 'admin': resp[0] if resp else payload}
        if isinstance(resp, dict) and resp.get('code'):
            return {'ok': False, 'error': resp.get('message', 'DB error')}
        return {'ok': True, 'admin': payload}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def remove_admin(telegram_user_id: str) -> Dict:
    if not _is_configured():
        return {'ok': False, 'error': 'Supabase not configured'}
    if telegram_user_id in SUPER_ADMIN_IDS:
        return {'ok': False, 'error': 'Cannot remove super-admin from env'}
    try:
        url = f"{SUPABASE_URL}/rest/v1/whale_admins?telegram_user_id=eq.{telegram_user_id}"
        headers = _headers()
        resp = requests.delete(url, headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            return {'ok': True, 'removed': telegram_user_id}
        return {'ok': False, 'error': f'HTTP {resp.status_code}: {resp.text[:200]}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
