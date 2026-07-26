"""
Large stablecoin (USDT, USDC, DAI, WBTC) transfers on Ethereum.
Uses Blockscout token transfers endpoint (free, no key).
"""
from typing import Optional, List
from ..http import fetch_json
from ..config import EXCHANGE_LABELS_ETH, log


# Token contracts (mainnet) - REAL, VERIFIED contracts
TOKEN_CONTRACTS = {
    '0xdac17f958d2ee523a2206206994597c13d831ec7': ('USDT', 6),   # Tether USD
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': ('USDC', 6),   # USD Coin
    '0x6b175474e89094c44da98b954eedeac495271d0f': ('DAI', 18),   # Dai Stablecoin
    '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': ('WBTC', 8),   # Wrapped BTC
}


def fetch_large_token_transfers(min_value_usd: float = 1_000_000, limit: int = 10) -> Optional[List]:
    """
    Fetch recent token transfers and filter by USD value.
    Returns list of: {hash, token, value, value_usd, from, to, asset, timestamp, contract}
    """
    out = []
    params = {'filter': 'validated'}
    base_url = 'https://eth.blockscout.com/api/v2/transactions'

    for page in range(3):
        data = fetch_json(base_url, params=params)
        if not data or 'items' not in data:
            break
        items = data['items']
        if not items:
            break
        for tx in items:
            try:
                token_transfers = tx.get('token_transfers', [])
                if not token_transfers or token_transfers is None:
                    continue
                for transfer in token_transfers[:5]:
                    token_obj = transfer.get('token', {})
                    if not isinstance(token_obj, dict):
                        continue
                    contract = token_obj.get('address', '').lower()
                    if contract in TOKEN_CONTRACTS:
                        symbol, decimals = TOKEN_CONTRACTS[contract]
                        try:
                            raw = int(transfer.get('total', '0'))
                            value = raw / (10 ** decimals)
                            # USD value
                            if symbol in ('USDT', 'USDC', 'DAI'):
                                value_usd = value
                            else:
                                # WBTC - will be priced by caller
                                value_usd = value  # placeholder

                            if value_usd >= min_value_usd:
                                from_obj = transfer.get('from', {})
                                to_obj = transfer.get('to', {})
                                from_addr = from_obj.get('hash', '') if isinstance(from_obj, dict) else ''
                                to_addr = to_obj.get('hash', '') if isinstance(to_obj, dict) else ''
                                out.append({
                                    'hash': tx.get('hash', ''),
                                    'token': symbol,
                                    'value': value,
                                    'value_usd': value_usd,
                                    'from': from_addr,
                                    'to': to_addr,
                                    'asset': symbol,
                                    'timestamp': tx.get('timestamp', ''),
                                    'contract': contract,
                                })
                        except (ValueError, TypeError):
                            continue
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
