"""
Centralized price fetching. Tries multiple free APIs for redundancy.
CRITICAL: NEVER fabricates prices. Returns None if all sources fail.
"""
from typing import Optional, Dict
from ..http import fetch_json
from ..config import log


# In-process cache (15 seconds)
_price_cache: Dict[str, float] = {}
_price_cache_ts: Dict[str, float] = {}


def _cached(symbol: str) -> Optional[float]:
    import time
    if symbol in _price_cache:
        age = time.time() - _price_cache_ts.get(symbol, 0)
        if age < 15:
            return _price_cache[symbol]
    return None


def _set_cache(symbol: str, price: float) -> None:
    import time
    _price_cache[symbol] = price
    _price_cache_ts[symbol] = time.time()


def get_btc_price() -> Optional[float]:
    """Get BTC/USD spot price. Tries Coinbase, then Binance."""
    cached = _cached('BTC')
    if cached:
        return cached

    # Try Coinbase
    data = fetch_json('https://api.coinbase.com/v2/prices/BTC-USD/spot', timeout=8)
    if data and 'data' in data:
        try:
            p = float(data['data']['amount'])
            _set_cache('BTC', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    # Try Binance
    data = fetch_json('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=8)
    if data and 'price' in data:
        try:
            p = float(data['price'])
            _set_cache('BTC', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    # Try CoinGecko
    data = fetch_json('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=8)
    if data and 'bitcoin' in data:
        try:
            p = float(data['bitcoin']['usd'])
            _set_cache('BTC', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    log.warning("All BTC price sources failed")
    return None


def get_eth_price() -> Optional[float]:
    """Get ETH/USD spot price."""
    cached = _cached('ETH')
    if cached:
        return cached

    data = fetch_json('https://api.coinbase.com/v2/prices/ETH-USD/spot', timeout=8)
    if data and 'data' in data:
        try:
            p = float(data['data']['amount'])
            _set_cache('ETH', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    data = fetch_json('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT', timeout=8)
    if data and 'price' in data:
        try:
            p = float(data['price'])
            _set_cache('ETH', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    data = fetch_json('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd', timeout=8)
    if data and 'ethereum' in data:
        try:
            p = float(data['ethereum']['usd'])
            _set_cache('ETH', p)
            return p
        except (KeyError, ValueError, TypeError):
            pass

    log.warning("All ETH price sources failed")
    return None


def get_token_price(token: str) -> Optional[float]:
    """Get price for any token by symbol. Returns None if not found."""
    token = token.upper()
    if token in ('USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'FDUSD'):
        return 1.0  # stables peg to USD
    if token == 'WBTC':
        return get_btc_price()

    cached = _cached(token)
    if cached:
        return cached

    # Try Binance
    try:
        data = fetch_json(f'https://api.binance.com/api/v3/ticker/price?symbol={token}USDT', timeout=8)
        if data and 'price' in data:
            p = float(data['price'])
            _set_cache(token, p)
            return p
    except Exception:
        pass

    # Try CoinGecko (by symbol)
    try:
        cg_ids = {
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'AAVE': 'aave',
            'MATIC': 'matic-network',
            'SHIB': 'shiba-inu',
            'PEPE': 'pepe',
            'WLD': 'worldcoin-wld',
        }
        cg_id = cg_ids.get(token)
        if cg_id:
            data = fetch_json(f'https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd', timeout=8)
            if data and cg_id in data:
                p = float(data[cg_id]['usd'])
                _set_cache(token, p)
                return p
    except Exception:
        pass

    return None
