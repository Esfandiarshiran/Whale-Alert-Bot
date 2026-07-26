"""
TEST MODE — generate sample alerts with REAL data (latest transactions).

Use this to see what alerts look like IMMEDIATELY without waiting for
a $1M+ whale move. Fetches the latest large transaction from each source
(even below threshold) and formats it like a real alert, with a clear
"[TEST MODE]" marker so it's obvious it's not a real alert.

Usage:
    python -m src.test_mode              # send to all channels
    python -m src.test_mode --dry-run    # print to console, don't send

You can also trigger this via admin command:  /test
"""
import sys
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

from .analyzer import shorten_addr, _parse_timestamp
from .sources.btc import fetch_btc_large_txs, _fetch_tx_details
from .sources.eth import fetch_eth_large_txs
from .sources.stablecoin import fetch_large_token_transfers
from .sources.tron import fetch_tron_usdt_transfers
from .sources.prices import get_btc_price, get_eth_price, get_token_price
from .enrichment import enrich_eth_address, enrich_btc_address, enrich_trx_address, infer_direction
from .virality import get_tier, compute_whale_score, detect_cluster, fmt_usd, fmt_crypto
from .card_generator import generate_alert_card
from .formatter import format_alert
from .telegram import send_to_all_channels, build_share_buttons
from .cache import is_posted, mark_posted
from .config import log


TEST_MARKER = "🧪 [TEST MODE — sample alert, not a real whale move]"


def build_test_alert_btc() -> dict:
    """Fetch the latest BTC mempool tx (regardless of size) and build a test alert."""
    log.info("TEST: Fetching latest BTC mempool tx...")
    btc_price = get_btc_price() or 60000

    # Fetch recent txs with very low threshold (we just want the latest)
    txs = fetch_btc_large_txs(min_value_btc=0.01, limit=3)
    if not txs:
        return None

    # Pick the largest one (don't worry about threshold)
    tx = max(txs, key=lambda x: x['value_btc'])
    value_usd = tx['value_btc'] * btc_price

    from_data = enrich_btc_address(tx.get('from_addr', ''))
    to_data = enrich_btc_address(tx.get('to_addr', ''))
    direction = infer_direction(from_data, to_data)
    cluster = detect_cluster()
    is_new = from_data.get('is_new_wallet', False) or to_data.get('is_new_wallet', False)
    score_data = compute_whale_score(
        value_usd=value_usd,
        direction=direction['direction'],
        is_new_wallet=is_new,
        cluster_count=cluster.get('count', 0),
    )
    tier = get_tier(value_usd)

    return {
        'asset': 'BTC',
        'value_usd': value_usd,
        'crypto_amount': tx['value_btc'],
        'tier': tier,
        'direction': direction,
        'from': from_data,
        'to': to_data,
        'score': score_data['score'],
        'score_breakdown': score_data['breakdown'],
        'tx_id': tx['txid'],
        'tx_short': tx['txid'][:16] + '...',
        'timestamp': datetime.now(timezone.utc),
        'cluster': cluster,
        'is_first_seen': is_new,
        '_test_marker': True,
    }


def build_test_alert_eth() -> dict:
    """Fetch latest ETH tx (any size) and build a test alert."""
    log.info("TEST: Fetching latest ETH tx...")
    eth_price = get_eth_price() or 3000

    # Very low threshold — we just want the latest
    txs = fetch_eth_large_txs(min_value_eth=0.001, limit=5)
    if not txs:
        return None

    tx = max(txs, key=lambda x: x['value_eth'])
    value_usd = tx['value_eth'] * eth_price

    from_data = enrich_eth_address(tx.get('from', ''))
    to_data = enrich_eth_address(tx.get('to', ''))
    direction = infer_direction(from_data, to_data)
    cluster = detect_cluster()
    is_new = from_data.get('is_new_wallet', False) or to_data.get('is_new_wallet', False)
    score_data = compute_whale_score(
        value_usd=value_usd,
        direction=direction['direction'],
        is_new_wallet=is_new,
        cluster_count=cluster.get('count', 0),
    )
    tier = get_tier(value_usd)

    return {
        'asset': 'ETH',
        'value_usd': value_usd,
        'crypto_amount': tx['value_eth'],
        'tier': tier,
        'direction': direction,
        'from': from_data,
        'to': to_data,
        'score': score_data['score'],
        'score_breakdown': score_data['breakdown'],
        'tx_id': tx['hash'],
        'tx_short': tx['hash'][:16] + '...',
        'timestamp': _parse_timestamp(tx.get('timestamp')),
        'cluster': cluster,
        'is_first_seen': is_new,
        '_test_marker': True,
    }


def build_test_alert_tron() -> dict:
    """Fetch latest TRON USDT transfer and build a test alert."""
    log.info("TEST: Fetching latest TRON USDT transfer...")
    txs = fetch_tron_usdt_transfers(min_value_usd=1.0, limit=5)
    if not txs:
        return None

    tx = max(txs, key=lambda x: x['value'])
    value_usd = tx['value_usd']

    from_data = enrich_trx_address(tx.get('from', ''))
    to_data = enrich_trx_address(tx.get('to', ''))
    direction = infer_direction(from_data, to_data)
    cluster = detect_cluster()
    is_new = from_data.get('is_new_wallet', False) or to_data.get('is_new_wallet', False)
    score_data = compute_whale_score(
        value_usd=value_usd,
        direction=direction['direction'],
        is_new_wallet=is_new,
        cluster_count=cluster.get('count', 0),
    )
    tier = get_tier(value_usd)

    return {
        'asset': 'USDT (TRON)',
        'value_usd': value_usd,
        'crypto_amount': tx['value'],
        'tier': tier,
        'direction': direction,
        'from': from_data,
        'to': to_data,
        'score': score_data['score'],
        'score_breakdown': score_data['breakdown'],
        'tx_id': tx['hash'],
        'tx_short': tx['hash'][:16] + '...',
        'timestamp': _parse_timestamp(tx.get('timestamp')),
        'cluster': cluster,
        'is_first_seen': is_new,
        '_test_marker': True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print to console, do not send')
    parser.add_argument('--source', choices=['btc', 'eth', 'tron', 'all'], default='all',
                        help='Which source to test (default: all)')
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("TEST MODE - generating sample alerts with REAL recent data")
    log.info("=" * 60)

    alerts = []
    if args.source in ('btc', 'all'):
        a = build_test_alert_btc()
        if a:
            alerts.append(a)
    if args.source in ('eth', 'all'):
        a = build_test_alert_eth()
        if a:
            alerts.append(a)
    if args.source in ('tron', 'all'):
        a = build_test_alert_tron()
        if a:
            alerts.append(a)

    if not alerts:
        log.error("No test alerts could be generated (network issues?)")
        return 1

    log.info(f"Generated {len(alerts)} test alert(s)")

    for alert in alerts:
        message = format_alert(alert)
        # Prepend test marker
        message = f"{TEST_MARKER}\n\n" + message
        photo_path = generate_alert_card(alert)

        # Get txid_short for personalization deep link
        full_txid = alert.get('tx_id', '')
        txid_short = None
        if full_txid:
            clean_txid = full_txid
            for prefix in ('btc_', 'eth_', 'stable_', 'trx_usdt_'):
                if clean_txid.startswith(prefix):
                    clean_txid = clean_txid[len(prefix):]
            txid_short = clean_txid[:16] if clean_txid else None

        # Store alert metadata for personalization
        if txid_short:
            try:
                from .cache import store_alert_meta
                store_alert_meta(txid_short, alert)
            except Exception:
                pass

        # Get mood for vote buttons
        mood = 'neutral'
        try:
            from .virality import generate_insight
            insight = generate_insight(alert)
            mood = insight.get('mood', 'neutral')
        except Exception:
            pass

        if args.dry_run:
            print("\n" + "=" * 60)
            print(f"TEST ALERT — {alert['asset']} (source: real latest tx)")
            print("=" * 60)
            print(f"Score: {alert['score']}/100")
            print(f"Value: {fmt_usd(alert['value_usd'])}")
            print(f"Direction: {alert['direction']['arrow']} {alert['direction']['label']}")
            print(f"txid_short: {txid_short}")
            print(f"Card: {photo_path or '(none)'}")
            print()
            print(message)
            print("=" * 60)
        else:
            log.info(f"Sending TEST alert for {alert['asset']}...")
            buttons = build_share_buttons(message, mood=mood, txid_short=txid_short)
            result = send_to_all_channels(message, photo_path=photo_path, inline_buttons=buttons)
            log.info(f"Sent: {result['success']} ok, {result['failed']} failed")

    log.info("Test mode complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
