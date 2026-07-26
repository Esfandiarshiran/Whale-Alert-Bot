"""
Virality engine: features that make alerts shareable, distinctive, and addictive.

Whale Score (0-100) — TRANSPARENT calculation from real inputs:
  - USD value (40 pts max): bigger = more points
  - Direction significance (25 pts max): exchange_in/out > inter_exchange > cold_storage
  - Wallet novelty (20 pts max): brand-new wallet is more interesting
  - Cluster timing (15 pts max): moving in cluster with others = more interesting

CRITICAL: Score is COMPUTED FROM REAL DATA, never guessed. We disclose the formula.
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from .config import (
    TIER_MEGA_USD, TIER_LARGE_USD, TIER_WHALE_USD, TIER_SMALL_USD,
    CLUSTER_WINDOW_MIN, CLUSTER_MIN_COUNT, log,
)
from .cache import get_recent_alerts, record_alert


# =====================================================================
# TIER BADGES
# =====================================================================
def get_tier(value_usd: float) -> Dict:
    """Returns {emoji, name, color_hex} based on USD value."""
    if value_usd >= TIER_MEGA_USD:
        return {'emoji': '🐳', 'name': 'MEGA', 'color': '#E63946'}
    if value_usd >= TIER_LARGE_USD:
        return {'emoji': '🦈', 'name': 'LARGE', 'color': '#F77F00'}
    if value_usd >= TIER_WHALE_USD:
        return {'emoji': '🐋', 'name': 'WHALE', 'color': '#FCBF49'}
    if value_usd >= TIER_SMALL_USD:
        return {'emoji': '🐬', 'name': 'SMALL', 'color': '#06A77D'}
    return {'emoji': '🐟', 'name': 'MICRO', 'color': '#118AB2'}


# =====================================================================
# WHALE SCORE
# =====================================================================
def compute_whale_score(
    value_usd: float,
    direction: str,
    is_new_wallet: bool,
    cluster_count: int = 0,
) -> Dict:
    """
    Transparent score: 0-100.
    Returns {score, breakdown, tier}.
    """
    # 1) Value score (0-40) - logarithmic, max at $100M+
    if value_usd <= 0:
        v_score = 0
    else:
        # log scale: $1M = ~10 pts, $10M = ~20 pts, $100M = ~30 pts, $1B = ~40 pts
        v_score = min(40, 10 * math.log10(value_usd / 100_000))
        v_score = max(0, v_score)

    # 2) Direction score (0-25)
    direction_scores = {
        'exchange_in': 25,    # biggest market impact signal
        'exchange_out': 22,
        'inter_exchange': 15,
        'cold_storage': 10,
        'unknown': 5,
    }
    d_score = direction_scores.get(direction, 5)

    # 3) Wallet novelty (0-20)
    n_score = 20 if is_new_wallet else 8

    # 4) Cluster bonus (0-15) — extra weight if other whales active in same window
    if cluster_count >= CLUSTER_MIN_COUNT:
        c_score = 15
    elif cluster_count >= 2:
        c_score = 8
    elif cluster_count >= 1:
        c_score = 4
    else:
        c_score = 0

    total = round(v_score + d_score + n_score + c_score)
    total = max(0, min(100, total))

    breakdown = {
        'value_pts': round(v_score, 1),
        'direction_pts': d_score,
        'novelty_pts': n_score,
        'cluster_pts': c_score,
    }

    return {
        'score': total,
        'breakdown': breakdown,
        'tier': '🔥 CRITICAL' if total >= 80 else '⚡ HIGH' if total >= 60 else '📊 MEDIUM' if total >= 40 else '📉 LOW',
    }


# =====================================================================
# CLUSTER DETECTION
# =====================================================================
def detect_cluster(now: datetime = None) -> Dict:
    """
    Check how many whales moved in the last CLUSTER_WINDOW_MIN minutes.
    Returns {count, is_cluster, threshold, window_min, recent_alerts_summary}.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    recent = get_recent_alerts(CLUSTER_WINDOW_MIN)
    count = len(recent)
    is_cluster = count >= CLUSTER_MIN_COUNT
    # Sum USD value
    total_usd = sum(r.get('value_usd', 0) for r in recent)
    return {
        'count': count,
        'is_cluster': is_cluster,
        'threshold': CLUSTER_MIN_COUNT,
        'window_min': CLUSTER_WINDOW_MIN,
        'total_usd': total_usd,
        'recent': recent[-5:],  # last 5 for context
    }


def track_alert_for_cluster(alert: dict) -> None:
    """Call this for each posted alert so cluster detection works."""
    record_alert(alert)


# =====================================================================
# TIME-SINCE-LAST-ACTIVITY (for cold storage detection)
# =====================================================================
def format_last_seen(last_seen_iso: str) -> str:
    """Returns human-readable '47 days ago' or 'first time seen'."""
    if not last_seen_iso:
        return 'first time seen'
    try:
        last = datetime.fromisoformat(last_seen_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        days = delta.days
        if days == 0:
            hours = int(delta.total_seconds() // 3600)
            if hours == 0:
                minutes = int(delta.total_seconds() // 60)
                return f'{minutes} min ago'
            return f'{hours} hours ago'
        if days == 1:
            return '1 day ago'
        if days < 30:
            return f'{days} days ago'
        if days < 365:
            months = days // 30
            return f'{months} months ago'
        years = days // 365
        return f'{years} years ago'
    except Exception:
        return 'unknown'


# =====================================================================
# "WHALE OF THE DAY" PICKER
# =====================================================================
def pick_whale_of_the_day(candidates: List[dict]) -> Optional[dict]:
    """Pick the most significant alert from a list.
    candidates: list of alert dicts with at least {value_usd, score, direction}"""
    if not candidates:
        return None
    # Sort by score, then by USD value
    sorted_c = sorted(
        candidates,
        key=lambda a: (a.get('score', 0), a.get('value_usd', 0)),
        reverse=True,
    )
    return sorted_c[0]


# =====================================================================
# INSIGHT ENGINE — interpretive layer that turns raw data into narrative
# This is what makes alerts SHAREABLE: people share stories, not numbers.
# =====================================================================
def generate_insight(alert: dict) -> Dict:
    """
    Generate a human-readable insight for an alert.
    Returns {headline, narrative, mood} where:
      - headline: 1-line punchy summary
      - narrative: 2-3 sentence context
      - mood: 'bullish' | 'bearish' | 'neutral' | 'caution'
    """
    value_usd = alert.get('value_usd', 0)
    asset = alert.get('asset', '?')
    direction = alert.get('direction', {})
    direction_type = direction.get('direction', 'unknown')
    from_d = alert.get('from', {})
    to_d = alert.get('to', {})
    is_first_seen = alert.get('is_first_seen', False)
    cluster = alert.get('cluster', {})
    score = alert.get('score', 0)

    from_label = from_d.get('label', 'Unlabeled')
    to_label = to_d.get('label', 'Unlabeled')
    from_exchange = from_d.get('is_exchange', False)
    to_exchange = to_d.get('is_exchange', False)

    # === Direction-based insights ===
    if direction_type == 'exchange_in' and to_exchange:
        exchange = to_d.get('exchange_name', 'an exchange')
        if value_usd >= 10_000_000:
            headline = f"🐋 Massive {fmt_usd(value_usd)} {asset} dump to {exchange}"
            narrative = (
                f"A whale just moved {fmt_usd(value_usd)} of {asset} into {exchange}. "
                f"Large inflows to exchanges often precede sell-offs as whales prepare to liquidate. "
                f"Watch {exchange}'s order books in the next 24-48h."
            )
            mood = 'bearish'
        else:
            headline = f"⚡ {fmt_usd(value_usd)} {asset} heading to {exchange}"
            narrative = (
                f"Funds moving to {exchange} — typically signals intent to sell. "
                f"Smaller size means limited immediate impact, but worth monitoring."
            )
            mood = 'caution'

    elif direction_type == 'exchange_out' and from_exchange:
        exchange = from_d.get('exchange_name', 'an exchange')
        if value_usd >= 10_000_000:
            headline = f"🟢 {fmt_usd(value_usd)} {asset} LEAVING {exchange}"
            narrative = (
                f"Major withdrawal from {exchange}. When whales pull funds off exchanges, "
                f"it usually means accumulation for long-term holding or cold storage. "
                f"This is structurally bullish — supply on exchanges shrinks."
            )
            mood = 'bullish'
        else:
            headline = f"📈 {fmt_usd(value_usd)} {asset} withdrawn from {exchange}"
            narrative = (
                f"Funds leaving {exchange} — typically accumulation or self-custody. "
                f"Reduces available sell liquidity on the exchange."
            )
            mood = 'bullish'

    elif direction_type == 'inter_exchange':
        f_name = from_d.get('exchange_name', '?')
        t_name = to_d.get('exchange_name', '?')
        headline = f"🔄 {fmt_usd(value_usd)} {asset}: {f_name} → {t_name}"
        narrative = (
            f"Inter-exchange transfer between {f_name} and {t_name}. "
            f"Often internal rebalancing or OTC desk activity. "
            f"Neutral for price, but indicates institutional flow."
        )
        mood = 'neutral'

    elif direction_type == 'cold_storage':
        # Check for first-seen
        if is_first_seen:
            headline = f"🆕 NEW whale wallet moves {fmt_usd(value_usd)} {asset}"
            narrative = (
                f"Brand-new wallet detected. Could be a freshly-funded cold storage, "
                f"an OTC settlement, or institutional positioning. "
                f"Unknown wallets are wildcards — track this address for future moves."
            )
            mood = 'caution'
        else:
            from_age = from_d.get('last_seen', '')
            to_age = to_d.get('last_seen', '')
            # If either wallet was dormant for a long time
            dormant_text = ''
            if from_age:
                age_str = format_last_seen(from_age)
                if 'months' in age_str or 'years' in age_str:
                    dormant_text = f"Sender wallet was dormant for {age_str} — "
            if not dormant_text and to_age:
                age_str = format_last_seen(to_age)
                if 'months' in age_str or 'years' in age_str:
                    dormant_text = f"Receiver wallet was dormant for {age_str} — "

            if dormant_text:
                headline = f"❄️ {fmt_usd(value_usd)} {asset} from dormant wallet"
                narrative = (
                    f"{dormant_text}dormant wallets waking up often signal "
                    f"long-term holders repositioning. Could be OTC, custody shift, "
                    f"or preparation for larger market activity."
                )
                mood = 'caution'
            else:
                headline = f"🔐 {fmt_usd(value_usd)} {asset} private transfer"
                narrative = (
                    f"Peer-to-peer movement between private wallets. "
                    f"Likely OTC desk, custody migration, or institutional transfer. "
                    f"No direct market impact, but worth tracking the wallets."
                )
                mood = 'neutral'
    else:
        headline = f"🐋 {fmt_usd(value_usd)} {asset} on the move"
        narrative = "Whale movement detected. Analyzing pattern..."
        mood = 'neutral'

    # === Cluster modifier ===
    if cluster and cluster.get('is_cluster'):
        count = cluster.get('count', 0)
        total_usd = cluster.get('total_usd', 0)
        headline += f"  [PART OF {count}-WHALE CLUSTER]"
        narrative += (
            f"\n\n⚠️  This is part of a cluster: {count} whales moved "
            f"a combined {fmt_usd(total_usd)} in the last 30 minutes. "
            f"Coordinated whale activity often precedes major market moves."
        )

    return {
        'headline': headline,
        'narrative': narrative,
        'mood': mood,
    }


# =====================================================================
# NUMBER FORMATTERS
# =====================================================================
def fmt_usd(value: float) -> str:
    """Format USD: $1.2M, $45.3K, $1.5B"""
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.1f}K"
    return f"${value:.0f}"


def fmt_crypto(value: float, asset: str = 'BTC') -> str:
    """Format crypto amount with appropriate decimals."""
    if value >= 1000:
        return f"{value:,.2f} {asset}"
    if value >= 1:
        return f"{value:,.4f} {asset}"
    return f"{value:,.6f} {asset}"


def fmt_pct(value: float) -> str:
    """Format percentage with sign: +3.2% / -1.4%"""
    sign = '+' if value >= 0 else ''
    return f"{sign}{value:.2f}%"
