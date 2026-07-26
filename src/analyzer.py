"""
Whale alert analyzer + orchestrator.

Pipeline:
1. Fetch prices (real-time, multiple sources)
2. Fetch large transactions from all chains (BTC, ETH, stablecoins, TRON USDT)
3. Enrich addresses (live labels, wallet memory, first-seen detection)
4. Infer direction (→ Exchange, ← Exchange, ↔ Cold storage, 🔄 Inter-exchange)
5. Compute Whale Score (0-100, transparent formula)
6. Detect clusters (4+ whales in 30 min = cluster alert)
7. Generate PNG card (for virality)
8. Build text message + inline share buttons
9. Return list of (message, photo_path, tx_id, alert_type, alert_meta) tuples

CRITICAL: Never raises. All failures degrade gracefully (skip source, skip alert).
"""
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict
from .sources.btc import fetch_btc_large_txs
from .sources.eth import fetch_eth_large_txs
from .sources.stablecoin import fetch_large_token_transfers
from .sources.tron import fetch_tron_usdt_transfers
from .sources.prices import get_btc_price, get_eth_price, get_token_price
from .cache import is_posted, mark_posted, record_flow, touch_wallet, add_weekly_candidate
from .enrichment import enrich_eth_address, enrich_btc_address, enrich_trx_address, infer_direction
from .virality import (
    get_tier, compute_whale_score, detect_cluster,
    track_alert_for_cluster, format_last_seen,
)
from .card_generator import generate_alert_card
from .formatter import format_alert, format_cluster_alert
from .config import (
    MIN_USD_BTC, MIN_USD_ETH, MIN_USD_STABLE, MIN_USD_TOKEN,
    TG_BATCH_MAX, log,
)


def shorten_addr(addr: str, prefix: int = 6, suffix: int = 4) -> str:
    if not addr:
        return 'Unknown'
    if len(addr) <= prefix + suffix + 2:
        return addr
    return f"{addr[:prefix]}...{addr[-suffix:]}"


def _parse_timestamp(ts) -> datetime:
    """Parse various timestamp formats to datetime."""
    if not ts:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            # ISO format
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        try:
            # Unix seconds
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def run_whale_scan() -> List[Tuple]:
    """
    Main scan function. Returns list of tuples:
      (message: str, photo_path: Optional[str], tx_id: str, alert_type: str, meta: dict)

    meta contains: {value_usd, asset, direction, score, is_cluster_alert, ...}
    """
    log.info("Starting whale scan v2...")
    alerts_to_send: List[Tuple] = []
    all_candidates: List[Dict] = []  # for whale-of-the-day picking

    # === 1. Prices ===
    btc_price = get_btc_price() or 60000
    eth_price = get_eth_price() or 3000
    log.info(f"Prices: BTC=${btc_price:,.0f}  ETH=${eth_price:,.0f}")

    # === 2. BTC ===
    try:
        btc_min_btc = MIN_USD_BTC / btc_price
        btc_txs = fetch_btc_large_txs(min_value_btc=btc_min_btc, limit=8)
        if btc_txs:
            log.info(f"BTC: {len(btc_txs)} large txs found")
            for tx in btc_txs:
                tx_id = f"btc_{tx['txid']}"
                if is_posted(tx_id):
                    continue
                value_usd = tx['value_btc'] * btc_price
                if value_usd < MIN_USD_BTC:
                    continue

                # Enrich addresses
                from_data = enrich_btc_address(tx.get('from_addr', ''))
                to_data = enrich_btc_address(tx.get('to_addr', ''))
                direction = infer_direction(from_data, to_data)

                # Cluster context
                cluster = detect_cluster()

                # Whale score
                is_new = from_data.get('is_new_wallet', False) or to_data.get('is_new_wallet', False)
                score_data = compute_whale_score(
                    value_usd=value_usd,
                    direction=direction['direction'],
                    is_new_wallet=is_new,
                    cluster_count=cluster.get('count', 0),
                )

                tier = get_tier(value_usd)
                ts = datetime.now(timezone.utc)

                alert_meta = {
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
                    'timestamp': ts,
                    'cluster': cluster,
                    'is_first_seen': is_new,
                }

                message = format_alert(alert_meta)
                photo_path = generate_alert_card(alert_meta)

                alerts_to_send.append((message, photo_path, tx_id, 'btc', alert_meta))
                all_candidates.append(alert_meta)
    except Exception as e:
        log.exception(f"BTC scan error: {e}")

    # === 3. ETH ===
    try:
        eth_min_eth = MIN_USD_ETH / eth_price
        eth_txs = fetch_eth_large_txs(min_value_eth=eth_min_eth, limit=10)
        if eth_txs:
            log.info(f"ETH: {len(eth_txs)} large txs found")
            for tx in eth_txs:
                tx_id = f"eth_{tx['hash']}"
                if is_posted(tx_id):
                    continue
                value_usd = tx['value_eth'] * eth_price
                if value_usd < MIN_USD_ETH:
                    continue

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
                ts = _parse_timestamp(tx.get('timestamp'))

                alert_meta = {
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
                    'timestamp': ts,
                    'cluster': cluster,
                    'is_first_seen': is_new,
                }
                message = format_alert(alert_meta)
                photo_path = generate_alert_card(alert_meta)
                alerts_to_send.append((message, photo_path, tx_id, 'eth', alert_meta))
                all_candidates.append(alert_meta)
    except Exception as e:
        log.exception(f"ETH scan error: {e}")

    # === 4. Stablecoins (Ethereum) ===
    try:
        stable_txs = fetch_large_token_transfers(min_value_usd=MIN_USD_STABLE, limit=8)
        if stable_txs:
            log.info(f"Stables: {len(stable_txs)} large transfers found")
            for tx in stable_txs:
                tx_id = f"stable_{tx['hash']}_{tx['token']}"
                if is_posted(tx_id):
                    continue
                value_usd = tx['value_usd']
                if value_usd < MIN_USD_STABLE:
                    continue
                # For WBTC, get real USD value
                if tx['token'] == 'WBTC':
                    wbtc_price = get_token_price('WBTC')
                    if wbtc_price:
                        value_usd = tx['value'] * wbtc_price
                        if value_usd < MIN_USD_TOKEN:
                            continue

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
                ts = _parse_timestamp(tx.get('timestamp'))

                alert_meta = {
                    'asset': tx['token'],
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
                    'timestamp': ts,
                    'cluster': cluster,
                    'is_first_seen': is_new,
                }
                message = format_alert(alert_meta)
                photo_path = generate_alert_card(alert_meta)
                alerts_to_send.append((message, photo_path, tx_id, 'stable', alert_meta))
                all_candidates.append(alert_meta)
    except Exception as e:
        log.exception(f"Stable scan error: {e}")

    # === 5. TRON USDT (BIG volume) ===
    try:
        trx_txs = fetch_tron_usdt_transfers(min_value_usd=MIN_USD_STABLE, limit=8)
        if trx_txs:
            log.info(f"TRON USDT: {len(trx_txs)} large transfers found")
            for tx in trx_txs:
                tx_id = f"trx_usdt_{tx['hash']}"
                if is_posted(tx_id):
                    continue
                value_usd = tx['value_usd']
                if value_usd < MIN_USD_STABLE:
                    continue

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
                ts = _parse_timestamp(tx.get('timestamp'))

                alert_meta = {
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
                    'timestamp': ts,
                    'cluster': cluster,
                    'is_first_seen': is_new,
                }
                message = format_alert(alert_meta)
                photo_path = generate_alert_card(alert_meta)
                alerts_to_send.append((message, photo_path, tx_id, 'stable', alert_meta))
                all_candidates.append(alert_meta)
    except Exception as e:
        log.exception(f"TRON scan error: {e}")

    # === 6. Sort by score (post the most significant first) ===
    alerts_to_send.sort(key=lambda x: x[4].get('score', 0), reverse=True)

    # === 7. Limit batch size (avoid spam) ===
    if len(alerts_to_send) > TG_BATCH_MAX:
        log.info(f"Batch limit: posting {TG_BATCH_MAX} of {len(alerts_to_send)} alerts")
        alerts_to_send = alerts_to_send[:TG_BATCH_MAX]

    # === 8. Record flow + cluster tracking for each alert ===
    for _, _, _, _, meta in alerts_to_send:
        try:
            direction = meta.get('direction', {}).get('direction', 'unknown')
            record_flow(direction, meta.get('value_usd', 0))
            track_alert_for_cluster({
                'timestamp': meta.get('timestamp', datetime.now(timezone.utc)).isoformat()
                              if isinstance(meta.get('timestamp'), datetime)
                              else str(meta.get('timestamp', '')),
                'value_usd': meta.get('value_usd', 0),
                'asset': meta.get('asset', ''),
                'direction': direction,
                'arrow': meta.get('direction', {}).get('arrow', '?'),
            })
        except Exception as e:
            log.debug(f"Flow tracking error: {e}")

        # === 8b. Register as weekly candidate (for Whale of the Week) ===
        try:
            add_weekly_candidate({
                'tx_id': meta.get('tx_id', ''),
                'asset': meta.get('asset', ''),
                'value_usd': meta.get('value_usd', 0),
                'score': meta.get('score', 0),
                'direction_label': meta.get('direction', {}).get('label', ''),
                'from_label': meta.get('from', {}).get('label', 'Unlabeled'),
                'to_label': meta.get('to', {}).get('label', 'Unlabeled'),
                'timestamp': meta.get('timestamp', datetime.now(timezone.utc)).isoformat()
                              if isinstance(meta.get('timestamp'), datetime)
                              else str(meta.get('timestamp', '')),
            })
        except Exception as e:
            log.debug(f"Weekly candidate tracking error: {e}")

    # === 9. Check for cluster alert (send AFTER individual alerts) ===
    cluster = detect_cluster()
    if cluster.get('is_cluster') and len(alerts_to_send) > 0:
        # Only send cluster alert if we haven't sent one in the last 30 min
        cluster_id = f"cluster_{datetime.now(timezone.utc).strftime('%Y%m%d_%H')}"
        if not is_posted(cluster_id):
            cluster_msg = format_cluster_alert(cluster)
            alerts_to_send.append((cluster_msg, None, cluster_id, 'cluster', {
                'value_usd': cluster.get('total_usd', 0),
                'asset': 'MULTI',
                'is_cluster_alert': True,
            }))

    log.info(f"Total new alerts to post: {len(alerts_to_send)}")
    return alerts_to_send
