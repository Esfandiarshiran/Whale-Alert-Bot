"""
Address enrichment layer.
- For Ethereum: queries Blockscout's address endpoint for live labels (real data)
- For Bitcoin: looks up in our verified table; if unknown, marks as 'Unlabeled'
- Direction inference: exchange_in / exchange_out / inter_exchange / cold_storage / unknown

CRITICAL: NEVER fabricates labels. If unknown, returns 'Unlabeled'.
"""
from typing import Dict, Tuple, Optional
from .config import (
    EXCHANGE_LABELS_ETH, EXCHANGE_LABELS_BTC, EXCHANGE_LABELS_TRX,
    get_label, classify_address, log,
)
from .http import fetch_json
from .cache import get_wallet, touch_wallet


# Cache for live-fetched labels (in-process, doesn't persist)
_LABEL_CACHE: Dict[str, str] = {}


def enrich_eth_address(addr: str) -> Dict:
    """
    Returns:
      {
        'address': original addr,
        'short': shortened,
        'label': human-readable label or 'Unlabeled',
        'is_exchange': bool,
        'exchange_name': str or '',
        'first_seen': ISO str or '',  # from our cache
        'last_seen': ISO str or '',
        'activity_count': int,
        'is_new_wallet': bool,  # first time we see this wallet
      }
    """
    if not addr:
        return _empty_enrichment()

    addr_lower = addr.lower()

    # 1) Check our verified static table first
    label = EXCHANGE_LABELS_ETH.get(addr_lower, '')
    if not label:
        # 2) Check live-fetched cache
        label = _LABEL_CACHE.get(addr_lower, '')
    if not label:
        # 3) Try live Blockscout lookup (only if not cached as 'Unlabeled')
        if _LABEL_CACHE.get(addr_lower, '__unknown__') != '__unknown__':
            label = _fetch_blockscout_label(addr)
            _LABEL_CACHE[addr_lower] = label or '__unknown__'
            if not label:
                label = ''
        else:
            label = ''

    is_exchange = bool(label) and label != 'Unlabeled'

    # 4) Wallet memory (from local cache)
    profile = get_wallet(addr, 'eth') or {}
    is_new = not profile
    touch_wallet(addr, 'eth', label)

    return {
        'address': addr,
        'short': _shorten(addr),
        'label': label if label else 'Unlabeled',
        'is_exchange': is_exchange,
        'exchange_name': label if is_exchange else '',
        'first_seen': profile.get('first_seen', ''),
        'last_seen': profile.get('last_seen', ''),
        'activity_count': profile.get('count', 0),
        'is_new_wallet': is_new,
    }


def enrich_btc_address(addr: str) -> Dict:
    """For BTC, we only use the static table. No live lookup (no free reliable API)."""
    if not addr:
        return _empty_enrichment()
    label = EXCHANGE_LABELS_BTC.get(addr, '')
    is_exchange = bool(label)
    profile = get_wallet(addr, 'btc') or {}
    is_new = not profile
    touch_wallet(addr, 'btc', label)
    return {
        'address': addr,
        'short': _shorten(addr),
        'label': label if label else 'Unlabeled',
        'is_exchange': is_exchange,
        'exchange_name': label if is_exchange else '',
        'first_seen': profile.get('first_seen', ''),
        'last_seen': profile.get('last_seen', ''),
        'activity_count': profile.get('count', 0),
        'is_new_wallet': is_new,
    }


def enrich_trx_address(addr: str) -> Dict:
    if not addr:
        return _empty_enrichment()
    addr_lower = addr.lower()
    label = EXCHANGE_LABELS_TRX.get(addr_lower, '')
    is_exchange = bool(label)
    profile = get_wallet(addr, 'trx') or {}
    is_new = not profile
    touch_wallet(addr, 'trx', label)
    return {
        'address': addr,
        'short': _shorten(addr),
        'label': label if label else 'Unlabeled',
        'is_exchange': is_exchange,
        'exchange_name': label if is_exchange else '',
        'first_seen': profile.get('first_seen', ''),
        'last_seen': profile.get('last_seen', ''),
        'activity_count': profile.get('count', 0),
        'is_new_wallet': is_new,
    }


def _fetch_blockscout_label(addr: str) -> str:
    """Fetch label from Blockscout's address endpoint. Returns '' if not found."""
    if not addr:
        return ''
    try:
        url = f"https://eth.blockscout.com/api/v2/addresses/{addr}"
        data = fetch_json(url, timeout=8)
        if not data or not isinstance(data, dict):
            return ''
        # Blockscout returns: name, tags, ens_domain_name
        name = data.get('name', '') or ''
        if name and isinstance(name, str) and name.strip():
            return name.strip()
        ens = data.get('ens_domain_name', '') or ''
        if ens and isinstance(ens, str) and ens.strip():
            return ens.strip()
        # Check tags
        tags = data.get('tags', [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict):
                    tname = tag.get('name') or tag.get('label') or ''
                    if tname and isinstance(tname, str):
                        return tname.strip()
        return ''
    except Exception as e:
        log.debug(f"Blockscout label fetch failed for {addr[:12]}: {e}")
        return ''


def _shorten(addr: str, prefix: int = 6, suffix: int = 4) -> str:
    if not addr:
        return 'Unknown'
    if len(addr) <= prefix + suffix + 2:
        return addr
    return f"{addr[:prefix]}...{addr[-suffix:]}"


def _empty_enrichment() -> Dict:
    return {
        'address': '', 'short': 'Unknown', 'label': 'Unlabeled',
        'is_exchange': False, 'exchange_name': '',
        'first_seen': '', 'last_seen': '', 'activity_count': 0,
        'is_new_wallet': False,
    }


# =====================================================================
# Direction inference - the killer feature
# =====================================================================
def infer_direction(from_data: Dict, to_data: Dict) -> Dict:
    """
    Returns:
      {
        'direction': 'exchange_in' | 'exchange_out' | 'inter_exchange' | 'cold_storage' | 'unknown',
        'arrow': str,  # '→', '←', '↔', '🔄', '?'
        'label': str,  # human readable
        'implication': str,  # what this typically means
        'color': str,  # 'red', 'green', 'yellow', 'gray'
      }
    """
    f_ex = from_data.get('is_exchange', False)
    t_ex = to_data.get('is_exchange', False)
    f_name = from_data.get('exchange_name', '')
    t_name = to_data.get('exchange_name', '')

    # Both exchanges
    if f_ex and t_ex:
        return {
            'direction': 'inter_exchange',
            'arrow': '🔄',
            'label': f"Inter-exchange: {f_name} → {t_name}",
            'implication': 'Internal exchange rebalance — typically neutral for market price',
            'color': 'yellow',
        }
    # To exchange (likely sell)
    if t_ex and not f_ex:
        return {
            'direction': 'exchange_in',
            'arrow': '→',
            'label': f"→ Exchange ({t_name})",
            'implication': 'Funds moving TO exchange — typically associated with potential sell pressure',
            'color': 'red',
        }
    # From exchange (likely buy/withdraw)
    if f_ex and not t_ex:
        return {
            'direction': 'exchange_out',
            'arrow': '←',
            'label': f"← Exchange ({f_name})",
            'implication': 'Funds leaving exchange — typically associated with accumulation or cold-storage (potential bullish)',
            'color': 'green',
        }
    # Neither exchange - cold storage / OTC / private
    return {
        'direction': 'cold_storage',
        'arrow': '↔',
        'label': 'Private wallet transfer',
        'implication': 'Peer-to-peer movement (OTC desk, custody shift, or private transfer) — neutral unless wallet is known',
        'color': 'gray',
    }
