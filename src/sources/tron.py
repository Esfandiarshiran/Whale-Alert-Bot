"""
TRON large USDT transfers via TronGrid API (free, no API key required for basic use).
TRON is THE biggest network for USDT volume — much larger than Ethereum USDT.

Endpoint: https://api.trongrid.io/v1/contracts/{contract}/events?event_name=Transfer&limit=20
USDT TRC-20 contract: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
"""
from typing import Optional, List
from ..http import fetch_json
from ..config import EXCHANGE_LABELS_TRX, log


# USDT TRC-20 contract on TRON
USDT_TRC20_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
USDT_DECIMALS = 6


def fetch_tron_usdt_transfers(min_value_usd: float = 1_000_000, limit: int = 10) -> Optional[List]:
    """
    Fetch recent USDT TRC-20 transfers and filter by value.
    Returns list of: {hash, token, value, value_usd, from, to, asset, timestamp}
    """
    url = f"https://api.trongrid.io/v1/contracts/{USDT_TRC20_CONTRACT}/events"
    params = {
        'event_name': 'Transfer',
        'limit': 50,
        'order_by': 'block_timestamp,desc',
    }
    data = fetch_json(url, params=params, timeout=12)
    if not data or not isinstance(data, dict):
        return []
    if not data.get('success'):
        return []

    out = []
    for event in data.get('data', []) or []:
        try:
            result = event.get('result', {})
            from_addr = result.get('from', '')
            to_addr = result.get('to', '')
            raw_value = result.get('value', '0')
            # Tron addresses in events are in hex format (starting with 0x)
            # Convert to base58 if needed
            from_addr = _normalize_tron_addr(from_addr)
            to_addr = _normalize_tron_addr(to_addr)
            try:
                value = int(raw_value) / (10 ** USDT_DECIMALS)
            except (ValueError, TypeError):
                continue
            if value >= min_value_usd:
                tx_id = event.get('transaction_id', '')
                block_ts = event.get('block_timestamp', 0)
                # Convert ms to ISO
                ts_iso = ''
                if block_ts:
                    try:
                        from datetime import datetime, timezone
                        ts_iso = datetime.fromtimestamp(int(block_ts) / 1000, tz=timezone.utc).isoformat()
                    except Exception:
                        pass
                out.append({
                    'hash': tx_id,
                    'token': 'USDT',
                    'value': value,
                    'value_usd': value,  # USDT is ~$1
                    'from': from_addr,
                    'to': to_addr,
                    'asset': 'USDT',
                    'timestamp': ts_iso,
                    'chain': 'tron',
                })
        except Exception as e:
            log.debug(f"Tron event parse error: {e}")
            continue

    return out[:limit]


def _normalize_tron_addr(addr: str) -> str:
    """Convert hex Tron address to base58 if it's in hex format."""
    if not addr:
        return ''
    if addr.startswith('T') and len(addr) == 34:
        return addr  # already base58
    if addr.startswith('0x') and len(addr) == 42:
        # Convert hex to base58
        try:
            return _hex_to_base58(addr)
        except Exception:
            return addr
    return addr


def _hex_to_base58(hex_addr: str) -> str:
    """Convert Tron hex address to base58."""
    # Remove 0x prefix and add 0x41 prefix (Tron mainnet byte)
    hex_str = hex_addr[2:]  # remove 0x
    if len(hex_str) == 40:
        # Add 41 prefix for mainnet
        hex_str = '41' + hex_str
    elif len(hex_str) == 42 and hex_str.startswith('41'):
        pass  # already has prefix
    else:
        return hex_addr

    # Convert to bytes
    try:
        decoded = bytes.fromhex(hex_str)
    except Exception:
        return hex_addr

    # Add checksum (double SHA256, first 4 bytes)
    import hashlib
    checksum = hashlib.sha256(hashlib.sha256(decoded).digest()).digest()[:4]
    decoded_with_checksum = decoded + checksum

    # Base58 encode
    return _base58_encode(decoded_with_checksum)


_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def _base58_encode(data: bytes) -> str:
    """Base58 encode bytes."""
    n = int.from_bytes(data, 'big')
    result = ''
    while n > 0:
        n, r = divmod(n, 58)
        result = _ALPHABET[r] + result
    # Add '1' for each leading zero byte
    for b in data:
        if b == 0:
            result = '1' + result
        else:
            break
    return result


def label_tron_address(addr: str) -> str:
    if not addr:
        return 'Unlabeled'
    return EXCHANGE_LABELS_TRX.get(addr.lower(), 'Unlabeled')
