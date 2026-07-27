"""
Telegram message formatter.

Output format (text + optional photo card):
- Insight headline (the shareable hook)
- Header line with tier emoji + asset
- Hero amount (USD)
- Crypto amount
- Direction with arrow + interpretation
- Insight narrative (2-3 sentences of context)
- From/To with labels + wallet age
- Whale Score with breakdown
- Cluster badge (if applicable)
- Footer (the funnel)

CRITICAL: Plain text only (no parse_mode) to avoid Telegram markdown/HTML errors.
We use Unicode arrows/emojis which render reliably in Telegram.
"""
from datetime import datetime, timezone
from typing import Dict, Optional
from .config import FOOTER_TEXT
from .virality import (
    get_tier, compute_whale_score, format_last_seen,
    detect_cluster, generate_insight, fmt_usd, fmt_crypto, fmt_pct,
)


def format_alert(alert: Dict) -> str:
    """
    Build the text message for an alert.
    """
    asset = alert.get('asset', 'BTC')
    value_usd = alert.get('value_usd', 0)
    crypto_amount = alert.get('crypto_amount', 0)
    tier = alert.get('tier', get_tier(value_usd))
    direction = alert.get('direction', {})
    score = alert.get('score', 0)
    breakdown = alert.get('score_breakdown', {})
    cluster = alert.get('cluster', {})

    # === Generate insight (the shareable narrative) ===
    insight = generate_insight(alert)
    mood_emoji = {
        'bullish': '🟢',
        'bearish': '🔴',
        'caution': '🟡',
        'neutral': '⚪',
    }.get(insight.get('mood', 'neutral'), '⚪')

    lines = []

    # === Insight Headline (FIRST — this is what people screenshot) ===
    lines.append(insight.get('headline', ''))
    lines.append("━" * 30)

    # === Header (tier + asset) ===
    lines.append(f"{tier.get('emoji', '🐋')} {tier.get('name', 'WHALE')} — {asset}")

    # === Hero ===
    lines.append(f"💰  {fmt_usd(value_usd)}")
    lines.append(f"    {fmt_crypto(crypto_amount, asset)}")
    lines.append("")

    # === Direction ===
    arrow = direction.get('arrow', '?')
    dir_label = direction.get('label', 'Unknown')
    impl = direction.get('implication', '')
    if dir_label.startswith(('→', '←', '↔', '🔄')):
        dir_display = dir_label
    else:
        dir_display = f"{arrow}  {dir_label}"
    lines.append(dir_display)
    if impl:
        wrapped = _wrap(impl, 60)
        for w in wrapped:
            lines.append(f"    {w}")
    lines.append("")

    # === Insight narrative (the storytelling layer) ===
    narrative = insight.get('narrative', '')
    if narrative:
        lines.append(f"{mood_emoji}  MARKET CONTEXT")
        for para in narrative.split('\n\n'):
            for w in _wrap(para, 60):
                lines.append(f"    {w}")
            lines.append("")

    # === From/To ===
    from_d = alert.get('from', {})
    to_d = alert.get('to', {})
    from_label = from_d.get('label', 'Unlabeled')
    to_label = to_d.get('label', 'Unlabeled')
    from_short = from_d.get('short', 'Unknown')
    to_short = to_d.get('short', 'Unknown')

    # Wallet age (interesting for cold storage moves)
    from_last = from_d.get('last_seen', '')
    to_last = to_d.get('last_seen', '')
    if from_last:
        from_age = format_last_seen(from_last)
        if from_age != 'first time seen' and from_age != 'unknown':
            from_label += f"  (last active {from_age})"
    if to_last:
        to_age = format_last_seen(to_last)
        if to_age != 'first time seen' and to_age != 'unknown':
            to_label += f"  (last active {to_age})"

    lines.append(f"FROM  {from_label}")
    lines.append(f"      {from_short}")
    lines.append(f"TO    {to_label}")
    lines.append(f"      {to_short}")
    lines.append("")

    # === First-seen badge ===
    if alert.get('is_first_seen'):
        lines.append("🎯  FIRST-TIME WALLET DETECTED")
        lines.append("")

    # === Whale Score ===
    score_emoji = "🔥" if score >= 80 else "⚡" if score >= 60 else "📊" if score >= 40 else "📉"
    lines.append(f"{score_emoji}  Whale Score: {score}/100")
    if breakdown:
        lines.append(
            f"    value {breakdown.get('value_pts', 0):.0f} • "
            f"direction {breakdown.get('direction_pts', 0)} • "
            f"novelty {breakdown.get('novelty_pts', 0)} • "
            f"cluster {breakdown.get('cluster_pts', 0)}"
        )
    lines.append("")

    # === Cluster badge ===
    if cluster and cluster.get('is_cluster'):
        count = cluster.get('count', 0)
        window = cluster.get('window_min', 30)
        lines.append(f"🌊  CLUSTER ACTIVITY: {count} whales in last {window} min")
        lines.append("")

    # === TX + time ===
    tx_short = alert.get('tx_short', '')
    ts = alert.get('timestamp', datetime.now(timezone.utc))
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            ts = datetime.now(timezone.utc)
    time_str = ts.strftime('%H:%M UTC')
    lines.append(f"TX: {tx_short}")
    lines.append(f"Time: {time_str}")
    lines.append("")

    # === Footer (the funnel) ===
    lines.append("━" * 30)
    lines.append(FOOTER_TEXT)

    return "\n".join(lines)


def format_welcome_message() -> str:
    """Welcome message for first run — clean, organized, no ✅ emoji."""
    divider = "━" * 30
    lines = [
        f"🐋 WHALE ALERT BOT — ACTIVATED",
        divider,
        "",
        "Real-time on-chain whale tracking — now LIVE.",
        "",
        f"📡 WHAT YOU'LL SEE:",
        "   • BTC transfers > $1M  (mempool)",
        "   • ETH transfers > $500K  (Blockscout)",
        "   • Stablecoin transfers > $1M  (USDT/USDC/DAI)",
        "",
        f"🚀 WHAT MAKES US DIFFERENT:",
        "   • Whale Score (0-100) — instant significance",
        "   • Direction analysis:",
        "       → Exchange = sell pressure",
        "       ← Exchange = accumulation",
        "       ↔ Cold storage = private transfer",
        "   • Wallet memory — first-seen detection",
        "   • Cluster alerts — 4+ whales in 30 min",
        "   • Beautiful shareable cards",
        "",
        "✦ All data verifiable on-chain.",
        "✦ 100% free — built on public APIs.",
        "",
        divider,
        FOOTER_TEXT,
    ]
    return "\n".join(lines)


def format_daily_summary(stats: dict) -> str:
    """Daily summary message — clean, organized."""
    divider = "━" * 30
    now = datetime.now(timezone.utc)
    lines = [
        f"📊 DAILY WHALE DIGEST",
        divider,
        f"Period: last 24h (as of {now:%Y-%m-%d %H:%M} UTC)",
        "",
    ]
    
    total_alerts = stats.get('total_alerts', 0)
    lines.append(f"Total alerts: {total_alerts}")
    lines.append(f"   BTC: {stats.get('btc_count', 0)}")
    lines.append(f"   ETH: {stats.get('eth_count', 0)}")
    lines.append(f"   Stables: {stats.get('stable_count', 0)}")
    lines.append("")

    total_usd = stats.get('total_usd', 0)
    if total_usd > 0:
        lines.append(f"Total whale volume: {fmt_usd(total_usd)}")
        lines.append("")

    net_flow = stats.get('net_flow', 0)
    if net_flow > 0:
        lines.append(f"Net exchange INFLOW: +{fmt_usd(abs(net_flow))}")
        lines.append("   → Potential sell pressure (bearish)")
        lines.append("")
    elif net_flow < 0:
        lines.append(f"Net exchange OUTFLOW: -{fmt_usd(abs(net_flow))}")
        lines.append("   → Potential accumulation (bullish)")
        lines.append("")

    top = stats.get('top_whale')
    if top:
        lines.append(f"🏆 TOP WHALE OF THE DAY:")
        lines.append(f"   {top.get('emoji', '🐋')} {fmt_usd(top.get('value_usd', 0))} {top.get('asset', '')}")
        if top.get('direction_label'):
            lines.append(f"   {top.get('direction_label', '')}")
        if top.get('score'):
            lines.append(f"   Whale Score: {top.get('score')}/100")
        lines.append("")

    if total_alerts == 0:
        lines.append("No whale activity met the threshold today.")
        lines.append("Whale movements are intermittent — this is normal.")
        lines.append("")

    lines.append(divider)
    lines.append(FOOTER_TEXT)
    return "\n".join(lines)


def format_cluster_alert(cluster: dict) -> str:
    """Standalone cluster alert (sent when cluster is detected)."""
    count = cluster.get('count', 0)
    window = cluster.get('window_min', 30)
    total_usd = cluster.get('total_usd', 0)
    recent = cluster.get('recent', [])

    lines = [
        "🌊  CLUSTER ACTIVITY DETECTED",
        "━" * 30,
        f"⚡  {count} whale movements in last {window} minutes",
        f"💰  Total volume: {fmt_usd(total_usd)}",
        "",
        "This is unusual — multiple whales moving simultaneously",
        "often precedes significant market moves.",
        "",
        "Recent moves in this cluster:",
    ]
    for r in recent[-5:]:
        asset = r.get('asset', '?')
        usd = r.get('value_usd', 0)
        arrow = r.get('arrow', '?')
        lines.append(f"  • {fmt_usd(usd)} {asset}  {arrow}")
    lines.append("")
    lines.append("━" * 30)
    lines.append(FOOTER_TEXT)
    return "\n".join(lines)


def format_help_message(is_admin: bool = False) -> str:
    """Help message for /help command — clean format."""
    divider = "━" * 30
    lines = [
        f"🐋 WHALE ALERT BOT — HELP",
        divider,
        "",
        f"PUBLIC COMMANDS:",
        f"   /start       — Welcome message",
        f"   /help        — Show this help",
        f"   /status      — Bot status",
        f"   /stats       — Today's whale stats",
        "",
    ]
    if is_admin:
        lines += [
            f"ADMIN COMMANDS:",
            f"   /test [btc|eth|tron]  — Generate test alert",
            f"   /addchannel @username — Add a channel",
            f"   /addchannel -100123.. — Add by numeric ID",
            f"   /removechannel @username — Remove a channel",
            f"   /listchannels  — List all active channels",
            f"   /addadmin <user_id>    — Add an admin",
            f"   /removeadmin <user_id> — Remove an admin",
            f"   /listadmins    — List all admins",
            "",
        ]
    lines += [
        divider,
        FOOTER_TEXT,
    ]
    return "\n".join(lines)


def format_status_message(channels_count: int, stats: dict, diag: dict) -> str:
    divider = "━" * 30
    lines = [
        f"📊 BOT STATUS",
        divider,
        f"Active channels: {channels_count}",
        f"",
        f"Alerts posted (since last summary):",
        f"   BTC: {stats.get('btc', 0)}",
        f"   ETH: {stats.get('eth', 0)}",
        f"   Stables: {stats.get('stable', 0)}",
        f"   Total: {stats.get('total', 0)}",
        f"",
        f"Wallets tracked: {diag.get('wallets_tracked', 0)}",
        f"Alerts in memory: {diag.get('recent_alerts_count', 0)}",
        f"",
        divider,
        FOOTER_TEXT,
    ]
    return "\n".join(lines)


def _wrap(text: str, width: int = 60) -> list:
    """Word-wrap text to a given width."""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ''
    for w in words:
        test = (current + ' ' + w).strip()
        if len(test) <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def format_weekly_winner(winner: dict, runner_ups: list = None) -> str:
    """Format the Whale of the Week announcement message."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    lines = [
        "🏆  WHALE OF THE WEEK",
        "━" * 30,
        f"Period: {week_ago.strftime('%b %d')} — {now.strftime('%b %d, %Y')}",
        "",
    ]

    asset = winner.get('asset', '?')
    value_usd = winner.get('value_usd', 0)
    score = winner.get('score', 0)

    lines.append(f"👑  The biggest whale move this week:")
    lines.append("")
    lines.append(f"💰  {fmt_usd(value_usd)}")
    lines.append(f"    Asset: {asset}")
    lines.append(f"    Whale Score: {score}/100")
    lines.append("")

    dir_label = winner.get('direction_label', '')
    if dir_label:
        lines.append(f"Direction: {dir_label}")
        lines.append("")

    from_label = winner.get('from_label', 'Unlabeled')
    to_label = winner.get('to_label', 'Unlabeled')
    lines.append(f"FROM  {from_label}")
    lines.append(f"TO    {to_label}")
    lines.append("")

    if runner_ups:
        lines.append("📊  OTHER NOTABLE MOVES THIS WEEK:")
        for i, ru in enumerate(runner_ups[:4], 1):
            ru_usd = ru.get('value_usd', 0)
            ru_asset = ru.get('asset', '?')
            lines.append(f"  {i}. {fmt_usd(ru_usd)}  {ru_asset}")
        lines.append("")

    lines.append("━" * 30)
    lines.append(FOOTER_TEXT)
    return "\n".join(lines)
