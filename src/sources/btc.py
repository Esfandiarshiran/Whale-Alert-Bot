"""
BTC large transactions from mempool.space (free, no key, real-time).
- /mempool/recent  — recent mempool txs (gives value but NOT from/to)
- /tx/{txid}       — full tx details (gives vin/vout = from/to addresses)
"""
from typing import Optional, List
from ..http import fetch_json
from ..config import EXCHANGE_LABELS_BTC, log


def fetch_btc_large_txs(min_value_btc: float = 15.0, limit: int = 10) -> Optional[List]:
    """
    Fetch recent BTC mempool transactions and filter by value.
    For each large tx, fetch full details to get from/to addresses.

    Returns list of:
      {txid, value_btc, fee_sat, asset, from_addr, to_addr, has_details}
    """
    data = fetch_json('https://mempool.space/api/mempool/recent')
    if not data or not isinstance(data, list):
        return []

    # Filter large txs (by BTC value)
    candidates = []
    for tx in data:
        try:
            val_sat = int(tx.get('value', 0))
            val_btc = val_sat / 1e8
            if val_btc >= min_value_btc:
                candidates.append({
                    'txid': tx.get('txid', ''),
                    'value_btc': val_btc,
                    'fee_sat': int(tx.get('fee', 0)),
                    'asset': 'BTC',
                })
        except (ValueError, TypeError):
            continue

    # Limit to top N to avoid hammering API
    candidates.sort(key=lambda x: x['value_btc'], reverse=True)
    candidates = candidates[:limit]

    # For each, fetch full tx to get from/to
    out = []
    for tx in candidates:
        details = _fetch_tx_details(tx['txid'])
        if details:
            tx['from_addr'] = details.get('from_addr', '')
            tx['to_addr'] = details.get('to_addr', '')
            tx['has_details'] = True
        else:
            tx['from_addr'] = ''
            tx['to_addr'] = ''
            tx['has_details'] = False
        out.append(tx)

    return out


def _fetch_tx_details(txid: str) -> Optional[dict]:
    """
    Fetch full tx details from mempool.space.
    Returns: {from_addr, to_addr} - the largest input and largest output addresses.
    """
    if not txid:
        return None
    data = fetch_json(f'https://mempool.space/api/tx/{txid}', timeout=10)
    if not data or not isinstance(data, dict):
        return None

    # Find largest input address (the "from")
    from_addr = ''
    max_in_value = 0
    for vin in data.get('vin', []) or []:
        v = vin.get('prevout', {})
        if v and isinstance(v, dict):
            val = v.get('value', 0)
            if val > max_in_value:
                max_in_value = val
                from_addr = v.get('scriptpubkey_address', '') or ''

    # Find largest output address (the "to")
    to_addr = ''
    max_out_value = 0
    for vout in data.get('vout', []) or []:
        val = vout.get('value', 0)
        if val > max_out_value:
            max_out_value = val
            to_addr = vout.get('scriptpubkey_address', '') or ''

    return {'from_addr': from_addr, 'to_addr': to_addr}


def label_btc_address(addr: str) -> str:
    """Try to label a BTC address. Returns 'Unlabeled' if not found."""
    if not addr:
        return 'Unlabeled'
    return EXCHANGE_LABELS_BTC.get(addr, 'Unlabeled')
