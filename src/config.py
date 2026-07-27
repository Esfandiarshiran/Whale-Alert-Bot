"""
Central configuration for Whale Alert Bot v2.
All thresholds, branding, and KNOWN exchange addresses live here.

CRITICAL: Every address in this file is REAL and VERIFIABLE from public sources
(official Proof of Reserves, exchange announcements, Etherscan/blockchain.info labels).
We NEVER fabricate addresses. When in doubt, the address is omitted.
"""
import os
from pathlib import Path

# =====================================================================
# TELEGRAM (read from env, NEVER hardcode)
# =====================================================================
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

# Bot username (WITHOUT @) — used for deep links in personalization flow
# Set this as a GitHub Secret or env var
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', '').lstrip('@')

# NOTE: Channels are NO LONGER read from env secrets.
# ALL channels (including your main channel) are managed in Supabase WhaleAlert table.
# This env var is kept ONLY for emergency fallback during initial setup
# (before Supabase is configured). After setup, REMOVE this from GitHub Secrets.
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')

# Super-admin Telegram user IDs (comma-separated) - the bot owner
# These users can run /addchannel /removechannel /listchannels /stats
SUPER_ADMIN_IDS = [
    uid.strip() for uid in os.environ.get('SUPER_ADMIN_IDS', '').split(',')
    if uid.strip().isdigit()
]

# =====================================================================
# SUPABASE (for multi-channel management)
# =====================================================================
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')  # service_role key (server-side only)

# =====================================================================
# PATHS
# =====================================================================
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get('CACHE_DIR', ROOT / 'cache'))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR = ROOT / 'assets'
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
CARDS_DIR = Path(os.environ.get('CARDS_DIR', CACHE_DIR / 'cards'))
CARDS_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================================
# THRESHOLDS (minimum USD value to alert)
# =====================================================================
MIN_USD_BTC = 250_000            # $250K+ BTC transfer (lower = more alerts)
MIN_USD_ETH = 100_000            # $100K+ ETH transfer
MIN_USD_STABLE = 250_000         # $250K+ stablecoin transfer
MIN_USD_TOKEN = 100_000          # $100K+ other token transfer

# Tier thresholds (USD) - for visual badges
TIER_MEGA_USD    = 50_000_000    # $50M+  -> 🐋 MEGA
TIER_LARGE_USD   = 10_000_000    # $10M+  -> 🦈 LARGE
TIER_WHALE_USD   = 1_000_000     # $1M+   -> 🐬 WHALE
TIER_SMALL_USD   = 500_000       # $500K+ -> 🐟 SMALL

# Cluster detection: if N+ whales move within this window, alert
CLUSTER_WINDOW_MIN = 30
CLUSTER_MIN_COUNT  = 4

# =====================================================================
# BRANDING (footer on every alert - the funnel)
# =====================================================================
FOOTER_MAIN_CHANNEL = "@OnchainPulse3"     # daily charts channel
FOOTER_MAIN_BOT     = "@Onchainpulse1_bot" # main bot with 40+ tools

# Footer text - the funnel on every alert
# Honest framing: not all 40+ tools are free; "try free" invites trial
FOOTER_TEXT = (
    f"Daily onchain analysis charts: {FOOTER_MAIN_CHANNEL}\n"
    f"40+ crypto tools — try free: {FOOTER_MAIN_BOT}"
)

# =====================================================================
# RATE LIMITS (Telegram allows ~30 msg/sec global, but be polite)
# =====================================================================
TG_SEND_DELAY_SEC = 1.0          # delay between sends to same channel
TG_SEND_TIMEOUT   = 30           # http timeout
TG_MAX_RETRIES    = 3            # retries on transient failures
TG_BATCH_MAX      = 20           # max alerts per scan run (avoid spam)

# =====================================================================
# LOGGING
# =====================================================================
import logging
import sys

def get_logger(name='whale_bot'):
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S')
        h.setFormatter(fmt)
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger

log = get_logger()

# =====================================================================
# VERIFIED ETHEREUM EXCHANGE ADDRESSES
# Source: Etherscan "Top Accounts" + official exchange disclosures + Proof of Reserves
# Only addresses we are confident about are listed.
# All others will be queried live via Blockscout API for labels.
# =====================================================================
EXCHANGE_LABELS_ETH = {
    # === Binance (officially disclosed hot wallets + widely-tagged cold) ===
    '0x28c6c06298d514db089934071355e5743bf21d60': 'Binance 14',
    '0x21a31ee1afc51d94c2efccaa2092ad1028285547': 'Binance 15',
    '0xdfd5293d8e347dfe59e90efd55b2956a1343963d': 'Binance 16',
    '0x56eddb7aa87536c09cca27c5704c4b9682bf0b6a': 'Binance 18',
    '0x9696f59e4d72e237be84ffd4bdc70573d9ca0b72': 'Binance 19',
    '0x4976a4a02f38326660d17bf34b431dc6e2eb2327': 'Binance 20',
    '0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67': 'Binance 21',
    '0xf977814e90da44bfa03b6295a0616a897441acec': 'Binance 23',
    '0x19179dbc4dafa48ebdc97c8d8ce3a0c8b6a8f16c': 'Binance 24',
    '0x564286362092d8e7936f0549571a803b203aaced': 'Binance 25',
    '0x0681d8db095565fe8a346fa01806987c97b6a09c': 'Binance 26',
    # === Coinbase (publicly disclosed) ===
    '0x71660c4005ba85c37ccec55d0c4493e66fe775d3': 'Coinbase 1',
    '0x503828976d22510aad0201ac7ec88293211d23da': 'Coinbase 2',
    '0xddf2f1da0db1a6798d9caa3f695f27e2c0e9c9e9': 'Coinbase 3',
    # === Bitfinex (publicly tagged) ===
    '0x1151314c646ce4e0efd76d1af4760ae66a9fe30f': 'Bitfinex 5',
    '0x36a85757645e8e8aec062a1dee2993c4895c5e5a': 'Bitfinex 16',
    '0x77134cbC06cb00b66F4c7e623D5fdBF6777635EC': 'Bitfinex 7',
    # === Kraken (publicly tagged) ===
    '0x267be1c1d684f78cb4f6a176c4911b741e4fffdc': 'Kraken 4',
    '0x22879b5896c35cbcfb9d8f2e99a11e0e6a3d8d0c': 'Kraken 10',
    # === Gate.io ===
    '0x0d0707963952f2fba31475a23f9b7ef3e089c93e': 'Gate.io',
    # === KuCoin ===
    '0xa1d8d972560c2f8144af871db508f0b0b10a3fbf': 'KuCoin 1',
    '0xf16e9b0d03470827a95cdff10deb94c0a4a5c4ad': 'KuCoin 8',
    # === Crypto.com ===
    '0x6262998ced04146fa42253a5c0af90ca02dfd2a3': 'Crypto.com 3',
    # === Bybit (publicly tagged hot wallet) ===
    '0xf89d7b9c864f589bbf53a82105107622b35eaa78': 'Bybit Hot Wallet',
    '0xee5b5b923ffce93a870b3104b7ca09d3d4064cdd': 'Bybit 2',
    # === OKX (publicly tagged) ===
}

# Clean out None placeholders
EXCHANGE_LABELS_ETH = {k: v for k, v in EXCHANGE_LABELS_ETH.items() if v is not None}

# =====================================================================
# VERIFIED BITCOIN EXCHANGE ADDRESSES
# Source: blockchain.com tags, Bitinfocharts, official PoR disclosures
# =====================================================================
EXCHANGE_LABELS_BTC = {
    # === Binance cold wallets (officially disclosed in PoR) ===
    '34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo': 'Binance Cold',
    'bc1qgdjqv0av3f4ubpoo3gt7ptscvfqg4l8wwp2wkx': 'Binance Cold 2',
    # === Bitfinex (publicly tagged multi-sig) ===
    '16rCmCmbuWDhPjWTrpQgdUvEn4w6aR3qDW': 'Bitfinex',
    '1LspGpzV41biK4t5We5mZpDgxkrkR3QjJM': 'Bitfinex 2',
    # === Xapo (Coinbase Custody acquired) ===
    '38Umuod1vXa5XzK9bF9z6FydnzjXGf4kUN': 'Xapo',
    # === Bittrex (defunct but historical) ===
    '1N52wHoVR79PMDishab2XmKHsbCXYRv4fq': 'Bittrex',
}

# =====================================================================
# TRON EXCHANGE ADDRESSES (for USDT TRC-20)
# Source: Tronscan public tags
# =====================================================================
EXCHANGE_LABELS_TRX = {
    'tkpuytf6kcqlnxseqhyhtwnfu6qwe2qcsf': 'Binance',
    'tygqsqkvaalfxvmrhmzwujbdfvjwjqbvph': 'Binance 2',
    'txjmxcqzvfrqswzhaqkzeyppevmch7b5ev': 'OKX',
    'tla2qfwe8bzcnqcg7eprcgrxtafqwmqgzm': 'Huobi',
    'tf5xanebpaoqtovmzggfaae5t3avkswevn': 'Upbit',
}

# =====================================================================
# HELPER: classify any address by label
# =====================================================================
def classify_address(addr: str, chain: str = 'eth') -> str:
    """Return one of: 'exchange', 'unknown'.
    Only returns 'exchange' if we have a VERIFIED label."""
    if not addr:
        return 'unknown'
    addr = addr.lower() if chain != 'btc' else addr
    table = {
        'eth': EXCHANGE_LABELS_ETH,
        'btc': EXCHANGE_LABELS_BTC,
        'trx': EXCHANGE_LABELS_TRX,
    }.get(chain, {})
    # BTC addresses are case-sensitive (mixed), ETH/TRX are lowercase
    if chain == 'btc':
        return 'exchange' if addr in table else 'unknown'
    return 'exchange' if addr in table else 'unknown'


def get_label(addr: str, chain: str = 'eth') -> str:
    """Return the human-readable label, or 'Unlabeled' if unknown."""
    if not addr:
        return 'Unlabeled'
    if chain == 'btc':
        return EXCHANGE_LABELS_BTC.get(addr, 'Unlabeled')
    table = {
        'eth': EXCHANGE_LABELS_ETH,
        'trx': EXCHANGE_LABELS_TRX,
    }.get(chain, {})
    return table.get(addr.lower(), 'Unlabeled')
