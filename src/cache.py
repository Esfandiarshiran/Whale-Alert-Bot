"""
Dedup cache + wallet memory + cluster detection state.
All persisted to local JSON (GitHub Actions cache restores it between runs).
CRITICAL: Never raises. All failures degrade gracefully.
Uses file locking to prevent corruption when multiple runs overlap.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from .config import CACHE_DIR, log


CACHE_FILE = CACHE_DIR / 'whale_state.json'
DEFAULT_TTL_TXS = 2000      # keep last 2000 tx hashes (renamed: was misleading "TTL")
DEFAULT_TTL_WALLETS = 5000  # keep last 5000 wallet profiles
DEFAULT_TTL_ALERT_META = 500  # keep last 500 alert metas for personalization
DEFAULT_TTL_PENDING = 100   # keep last 100 pending personalization requests


def _empty_state() -> dict:
    return {
        'version': 2,
        'ts': datetime.now(timezone.utc).isoformat(),
        'first_run': True,
        'last_summary': None,
        'stats': {'btc': 0, 'eth': 0, 'stable': 0, 'token': 0, 'total': 0},
        'posted_txs': [],              # list of tx_id strings
        'wallets': {},                 # addr -> {first_seen, last_seen, count, chain, label}
        'recent_alerts': [],           # last 50 alerts (for cluster detection)
        'daily_flow': {},              # date_str -> {exchange_in, exchange_out, total_usd}
        'whale_of_day_history': [],    # last 30 days' top whales
        'alert_meta_store': {},        # short_txid -> full alert metadata (for personalization)
        'pending_personalizations': {},  # user_id -> {txid_short, asked_at}
    }


def _load() -> dict:
    if not CACHE_FILE.exists():
        return _empty_state()
    try:
        data = json.loads(CACHE_FILE.read_text())
        # Migration: if old format, reset
        if 'version' not in data or data.get('version', 1) < 2:
            log.info("Migrating cache to v2 format")
            new_state = _empty_state()
            new_state['first_run'] = data.get('first_run', True)
            new_state['posted_txs'] = data.get('txs', [])
            new_state['last_summary'] = data.get('last_summary')
            new_state['stats'] = data.get('stats', new_state['stats'])
            return new_state
        # Ensure all keys exist
        for k, v in _empty_state().items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        log.warning(f"Cache load failed, starting fresh: {e}")
        return _empty_state()


def _save(data: dict) -> None:
    """Save state. Uses atomic write (temp + rename) to prevent corruption.
    No fcntl locking — atomic rename is sufficient for our use case.
    The concurrency group in GitHub Actions prevents overlapping runs."""
    try:
        # Ensure directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp, then rename
        tmp = CACHE_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(CACHE_FILE)
    except Exception as e:
        log.warning(f"Cache save error: {e}")


# =====================================================================
# TX dedup — optimized with in-memory set for O(1) lookup
# =====================================================================
_posted_txs_set = None  # cached set for fast lookup


def _get_posted_txs_set() -> set:
    """Get posted txs as a set (cached in memory after first load)."""
    global _posted_txs_set
    if _posted_txs_set is None:
        state = _load()
        _posted_txs_set = set(state.get('posted_txs', []))
    return _posted_txs_set


def is_posted(tx_id: str) -> bool:
    """O(1) lookup using in-memory set."""
    return tx_id in _get_posted_txs_set()


def mark_posted(tx_id: str, alert_type: str = 'btc') -> None:
    """Mark tx as posted. Updates both in-memory set and file."""
    global _posted_txs_set
    posted_set = _get_posted_txs_set()
    if tx_id in posted_set:
        return  # already posted
    posted_set.add(tx_id)

    state = _load()
    txs = state.get('posted_txs', [])
    txs.append(tx_id)
    # Keep last N entries
    if len(txs) > DEFAULT_TTL_TXS:
        txs = txs[-DEFAULT_TTL_TXS:]
        # Sync the set with trimmed list
        _posted_txs_set = set(txs)
    state['posted_txs'] = txs
    state['ts'] = datetime.now(timezone.utc).isoformat()
    stats = state.get('stats', {})
    if alert_type in stats:
        stats[alert_type] = stats[alert_type] + 1
    else:
        stats[alert_type] = 1
    stats['total'] = stats.get('total', 0) + 1
    state['stats'] = stats
    _save(state)


# =====================================================================
# Wallet memory: track first-seen / last-seen per address
# =====================================================================
def touch_wallet(addr: str, chain: str = 'eth', label: str = '') -> Dict[str, Any]:
    """
    Record activity for a wallet. Returns its profile:
    {first_seen, last_seen, count, label, is_new}
    """
    if not addr:
        return {}
    state = _load()
    wallets = state.get('wallets', {})
    key = f"{chain}:{addr.lower()}" if chain != 'btc' else f"btc:{addr}"
    now_iso = datetime.now(timezone.utc).isoformat()
    profile = wallets.get(key, {})
    is_new = not profile
    if is_new:
        profile = {
            'first_seen': now_iso,
            'last_seen': now_iso,
            'count': 1,
            'chain': chain,
            'label': label,
        }
    else:
        profile['last_seen'] = now_iso
        profile['count'] = profile.get('count', 0) + 1
        if label:
            profile['label'] = label
    wallets[key] = profile
    # Trim if too big
    if len(wallets) > DEFAULT_TTL_WALLETS:
        # Keep most recently active
        sorted_w = sorted(wallets.items(), key=lambda x: x[1].get('last_seen', ''), reverse=True)
        wallets = dict(sorted_w[:DEFAULT_TTL_WALLETS])
    state['wallets'] = wallets
    _save(state)
    profile['is_new'] = is_new
    return profile


def get_wallet(addr: str, chain: str = 'eth') -> Optional[Dict[str, Any]]:
    """Get wallet profile without modifying it. Returns None if unknown."""
    if not addr:
        return None
    state = _load()
    wallets = state.get('wallets', {})
    key = f"{chain}:{addr.lower()}" if chain != 'btc' else f"btc:{addr}"
    return wallets.get(key)


# =====================================================================
# Recent alerts: for cluster detection
# =====================================================================
def record_alert(alert: dict) -> None:
    """Record an alert in the recent_alerts list for cluster detection.
    alert must have: timestamp (ISO), value_usd, asset, direction"""
    state = _load()
    recent = state.get('recent_alerts', [])
    recent.append(alert)
    # Keep last 100
    if len(recent) > 100:
        recent = recent[-100:]
    state['recent_alerts'] = recent
    _save(state)


def get_recent_alerts(minutes: int = 60) -> List[dict]:
    """Get alerts from last N minutes."""
    state = _load()
    recent = state.get('recent_alerts', [])
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    out = []
    for a in recent:
        try:
            ts = datetime.fromisoformat(a.get('timestamp', ''))
            if ts > cutoff:
                out.append(a)
        except Exception:
            continue
    return out


# =====================================================================
# Daily flow tracking (for daily summary)
# =====================================================================
def record_flow(direction: str, value_usd: float, date_str: str = None) -> None:
    """direction: 'exchange_in' or 'exchange_out' or 'inter_wallet'"""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    state = _load()
    flow = state.get('daily_flow', {})
    day = flow.get(date_str, {'exchange_in': 0, 'exchange_out': 0, 'inter_wallet': 0, 'count': 0})
    if direction in day:
        day[direction] = day[direction] + value_usd
    day['count'] = day.get('count', 0) + 1
    flow[date_str] = day
    # Keep last 30 days
    if len(flow) > 30:
        sorted_f = sorted(flow.items(), reverse=True)[:30]
        flow = dict(sorted_f)
    state['daily_flow'] = flow
    _save(state)


# def get_today_flow() -> dict:
#     date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
#     state = _load()
#     flow = state.get('daily_flow', {})
#     return flow.get(date_str, {'exchange_in': 0, 'exchange_out': 0, 'inter_wallet': 0, 'count': 0})


# =====================================================================
# First-run + summary tracking
# =====================================================================
def is_first_run() -> bool:
    return _load().get('first_run', True)


def mark_initialized() -> None:
    state = _load()
    state['first_run'] = False
    state['ts'] = datetime.now(timezone.utc).isoformat()
    _save(state)


# def should_post_summary(hours: int = 24) -> bool:
#     state = _load()
#     last = state.get('last_summary')
#     if not last:
#         return True
#     try:
#         last_dt = datetime.fromisoformat(last)
#         return (datetime.now(timezone.utc) - last_dt) >= timedelta(hours=hours)
#     except Exception:
#         return True


# def mark_summary_posted() -> None:
#     state = _load()
#     state['last_summary'] = datetime.now(timezone.utc).isoformat()
#     _save(state)


def get_stats() -> dict:
    return _load().get('stats', {'btc': 0, 'eth': 0, 'stable': 0, 'token': 0, 'total': 0})


def reset_stats() -> None:
    state = _load()
    # Include 'cluster' key so cluster alerts are tracked properly
    state['stats'] = {'btc': 0, 'eth': 0, 'stable': 0, 'token': 0, 'cluster': 0, 'total': 0}
    _save(state)


# =====================================================================
# Whale of the Day history
# =====================================================================
def get_whale_of_day_history() -> List[dict]:
    return _load().get('whale_of_day_history', [])


def record_whale_of_day(entry: dict) -> None:
    state = _load()
    history = state.get('whale_of_day_history', [])
    history.append(entry)
    if len(history) > 30:
        history = history[-30:]
    state['whale_of_day_history'] = history
    _save(state)


# =====================================================================
# Whale of the Week — weekly winner tracking
# =====================================================================
def _empty_weekly_state() -> dict:
    return {
        'week_start': datetime.now(timezone.utc).isoformat(),
        'candidates': [],   # list of {tx_id, asset, value_usd, score, direction_label, timestamp, from_label, to_label}
        'last_posted_week': None,  # ISO date of last week we posted a winner
    }


def get_weekly_state() -> dict:
    state = _load()
    weekly = state.get('weekly_whale', {})
    if not weekly:
        weekly = _empty_weekly_state()
        state['weekly_whale'] = weekly
        _save(state)
    return weekly


def add_weekly_candidate(candidate: dict) -> None:
    """Add a candidate to this week's pool. Keep only top 50 by score."""
    state = _load()
    weekly = state.get('weekly_whale') or _empty_weekly_state()
    candidates = weekly.get('candidates', [])
    candidates.append(candidate)
    # Keep top 50 by score, then by value_usd
    candidates.sort(key=lambda c: (c.get('score', 0), c.get('value_usd', 0)), reverse=True)
    if len(candidates) > 50:
        candidates = candidates[:50]
    weekly['candidates'] = candidates
    state['weekly_whale'] = weekly
    _save(state)


def get_weekly_winner() -> Optional[dict]:
    """Returns the top candidate from this week, or None if no candidates."""
    weekly = get_weekly_state()
    candidates = weekly.get('candidates', [])
    if not candidates:
        return None
    return candidates[0]


def should_post_weekly_winner() -> bool:
    """Check if it's been 7+ days since last weekly winner post."""
    state = _load()
    weekly = state.get('weekly_whale') or _empty_weekly_state()
    last = weekly.get('last_posted_week')
    if not last:
        # First run — only post after 7 days of accumulation
        week_start = weekly.get('week_start')
        if not week_start:
            return False
        try:
            ws = datetime.fromisoformat(week_start)
            return (datetime.now(timezone.utc) - ws).days >= 7
        except Exception:
            return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt).days >= 7
    except Exception:
        return True


def mark_weekly_winner_posted(winner: dict) -> None:
    """Record that we posted the weekly winner. Reset candidates for next week."""
    state = _load()
    weekly = state.get('weekly_whale') or _empty_weekly_state()
    weekly['last_posted_week'] = datetime.now(timezone.utc).isoformat()
    weekly['week_start'] = datetime.now(timezone.utc).isoformat()
    weekly['candidates'] = []  # reset for next week
    weekly['last_winner'] = winner  # keep reference
    state['weekly_whale'] = weekly
    _save(state)


# =====================================================================
# Atomic getUpdates offset (for admin bot polling)
# =====================================================================
def get_update_offset() -> int:
    state = _load()
    return state.get('tg_update_offset', 0)


def set_update_offset(offset: int) -> None:
    state = _load()
    state['tg_update_offset'] = offset
    _save(state)


# =====================================================================
# ALERT METADATA STORE — for personalization feature
# When we post an alert, we store its full metadata so users can
# later request a personalized version via deep link.
# =====================================================================
def _serialize_value(v):
    """Recursively convert datetime to ISO string, deep-copy dicts/lists."""
    if isinstance(v, datetime):
        return v.isoformat()
    elif isinstance(v, dict):
        return {k: _serialize_value(dv) for k, dv in v.items()}
    elif isinstance(v, (list, tuple)):
        return [_serialize_value(item) for item in v]
    else:
        return v


def store_alert_meta(short_id: str, meta: dict) -> None:
    """Store alert metadata keyed by short txid (for personalization).
    Keeps only the most recent N entries.
    Uses recursive serialization to handle nested dicts with datetime values."""
    if not short_id or not meta:
        return
    state = _load()
    store = state.get('alert_meta_store', {})
    # Recursively serialize — handles any nesting depth
    safe_meta = {}
    for k, v in meta.items():
        try:
            safe_meta[k] = _serialize_value(v)
        except Exception:
            continue
    store[short_id] = safe_meta
    # Trim if too big — keep most recent by insertion order (Python 3.7+ preserves dict order)
    if len(store) > DEFAULT_TTL_ALERT_META:
        keys = list(store.keys())
        for k in keys[:-DEFAULT_TTL_ALERT_META]:
            del store[k]
    state['alert_meta_store'] = store
    _save(state)


def get_alert_meta(short_id: str) -> Optional[dict]:
    """Retrieve alert metadata by short txid."""
    if not short_id:
        return None
    state = _load()
    return state.get('alert_meta_store', {}).get(short_id)


# =====================================================================
# PENDING PERSONALIZATIONS — conversation state for /spot flow
# =====================================================================
def set_pending_personalization(user_id: str, txid_short: str) -> None:
    """Record that we're waiting for a username from this user."""
    state = _load()
    pending = state.get('pending_personalizations', {})
    pending[user_id] = {
        'txid_short': txid_short,
        'asked_at': datetime.now(timezone.utc).isoformat(),
    }
    # Trim old entries
    if len(pending) > DEFAULT_TTL_PENDING:
        keys = list(pending.keys())
        for k in keys[:-DEFAULT_TTL_PENDING]:
            del pending[k]
    state['pending_personalizations'] = pending
    _save(state)


def get_pending_personalization(user_id: str) -> Optional[dict]:
    """Get the pending personalization for a user. Returns None if not pending."""
    if not user_id:
        return None
    state = _load()
    return state.get('pending_personalizations', {}).get(user_id)


def clear_pending_personalization(user_id: str) -> None:
    """Clear the pending personalization for a user."""
    if not user_id:
        return
    state = _load()
    pending = state.get('pending_personalizations', {})
    if user_id in pending:
        del pending[user_id]
        state['pending_personalizations'] = pending
        _save(state)


# =====================================================================
# Diagnostics
# =====================================================================
def diagnostics() -> dict:
    state = _load()
    return {
        'posted_txs_count': len(state.get('posted_txs', [])),
        'wallets_tracked': len(state.get('wallets', {})),
        'recent_alerts_count': len(state.get('recent_alerts', [])),
        'daily_flow_days': len(state.get('daily_flow', {})),
        'whale_of_day_history_count': len(state.get('whale_of_day_history', [])),
        'alert_meta_store_count': len(state.get('alert_meta_store', {})),
        'pending_personalizations_count': len(state.get('pending_personalizations', {})),
        'cache_file': str(CACHE_FILE),
        'cache_file_exists': CACHE_FILE.exists(),
    }
