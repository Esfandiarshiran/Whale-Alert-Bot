"""
ETH large transactions from Blockscout (free, no key, real-time).
- /api/v2/transactions  — recent confirmed txs with values
"""
from typing import Optional, List
from ..http import fetch_json
from ..config import EXCHANGE_LABELS_ETH, log


def fetch_eth_large_txs(min_value_eth: float = 200.0, max_pages: int = 5, limit: int = 15) -> Optional[List]:
    """
    Fetch recent ETH transactions and filter by value.
    Returns list of: {hash, value_eth, from, to, asset, timestamp}
    """
    out = []
    params = {'filter': 'validated'}
    base_url = 'https://eth.blockscout.com/api/v2/transactions'

    for page in range(max_pages):
        data = fetch_json(base_url, params=params)
        if not data or 'items' not in data:
            break
        items = data['items']
        if not items:
            break
        for tx in items:
            try:
                val_wei = int(tx.get('value', '0'))
                val_eth = val_wei / 1e18
                if val_eth >= min_value_eth:
                    from_obj = tx.get('from') or {}
                    to_obj = tx.get('to') or {}
                    from_addr = from_obj.get('hash', '') if isinstance(from_obj, dict) else ''
                    to_addr = to_obj.get('hash', '') if isinstance(to_obj, dict) else ''
                    out.append({
                        'hash': tx.get('hash', ''),
                        'value_eth': val_eth,
                        'from': from_addr,
                        'to': to_addr,
                        'asset': 'ETH',
                        'timestamp': tx.get('timestamp', ''),
                        'fee': int(tx.get('fee', {}).get('value', '0')) if isinstance(tx.get('fee'), dict) else 0,
                    })
            except (ValueError, TypeError, AttributeError):
                continue
        npp = data.get('next_page_params')
        if not npp:
            break
        params = npp
        if len(out) >= limit:
            break

    return out[:limit]


def label_eth_address(addr: str) -> str:
    """Try to label an ETH address. Returns 'Unlabeled' if not found."""
    if not addr:
        return 'Unlabeled'
    return EXCHANGE_LABELS_ETH.get(addr.lower(), 'Unlabeled')
