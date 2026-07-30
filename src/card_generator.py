"""
PNG card generator v4 — MAGAZINE LAYOUT EDITION.

Completely redesigned from v3. New design philosophy:
- Magazine-style asymmetric layout (not centered/boring)
- Bold color blocks instead of subtle gradients
- Heavy use of contrast (large numbers vs small labels)
- Direction signal as a colored SIDE BAR (not a panel)
- Personalization banner as a "newspaper headline" strip
- Footer as a clean grid of CTAs (not text lines)
- Social icons row with distinct visual treatment

Layout (1080x1350 portrait):
  [TOP STRIP - dark] ............ tier + asset + date
  [HERO BLOCK - color] ......... massive USD value
  [SIDE BAR - direction color] . arrow + direction label
  [SPLIT ROW] .................. from | to (two columns)
  [SCORE STRIP] ................ whale score with bar
  [PERSONALIZATION] ............ spotted by @username (or placeholder)
  [FOOTER GRID - dark] ......... 4 CTAs in 2x2 grid
  [SOCIAL ROW] ................. twitter / telegram / share icons
"""
import os
import math
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from .config import CARDS_DIR, FOOTER_MAIN_CHANNEL, FOOTER_MAIN_BOT, log

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    log.warning("Pillow not installed - card generation disabled (text-only alerts)")


# =====================================================================
# CARD DIMENSIONS (portrait)
# =====================================================================
CARD_W = 1080
CARD_H = 1350

# =====================================================================
# MODERN COLOR PALETTE — high contrast, magazine-style
# =====================================================================
# Background: deep charcoal (not navy)
COLOR_BG         = (12, 12, 18)        # near-black charcoal
COLOR_BG_PANEL   = (22, 22, 32)        # slightly lighter for panels
COLOR_BG_TOP     = (8, 8, 14)          # top strip (darkest)
COLOR_BG_BOTTOM  = (6, 6, 12)          # bottom strip

# Accent: vibrant gold (not muted)
COLOR_GOLD       = (255, 200, 60)      # bright gold
COLOR_GOLD_DIM   = (160, 120, 30)      # for shadows

# Direction colors — vibrant, not pastel
COLOR_BULL       = (50, 220, 130)      # bright green
COLOR_BEAR       = (255, 80, 80)       # bright red
COLOR_NEUTRAL    = (180, 180, 200)     # cool gray
COLOR_WARN       = (255, 180, 50)      # orange

# Text
COLOR_WHITE      = (255, 255, 255)
COLOR_OFFWHITE   = (235, 235, 245)
COLOR_MUTED      = (140, 140, 160)
COLOR_DIM        = (90, 90, 110)

# Score bar
COLOR_SCORE_HIGH = (255, 80, 80)       # red for high significance
COLOR_SCORE_MID  = (255, 180, 50)      # orange
COLOR_SCORE_LOW  = (130, 200, 255)     # blue


# =====================================================================
# FONTS — bold sans for everything (modern magazine feel)
# =====================================================================
_FONT_BOLD = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
]
_FONT_REG = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
]
_FONT_BLACK = [
    '/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Black.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]
_FONT_MONO = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf',
]

_font_cache = {}


def _font(size: int, style: str = 'bold') -> ImageFont.FreeTypeFont:
    """Get a font. Styles: 'bold', 'reg', 'black', 'mono'."""
    if not PIL_AVAILABLE:
        return None
    cache_key = (size, style)
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    paths = {
        'bold': _FONT_BOLD,
        'reg': _FONT_REG,
        'black': _FONT_BLACK,
        'mono': _FONT_MONO,
    }.get(style, _FONT_BOLD)
    for p in paths:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _font_cache[cache_key] = f
                return f
            except Exception:
                continue
    try:
        f = ImageFont.load_default()
        _font_cache[cache_key] = f
        return f
    except Exception:
        return None


# =====================================================================
# HELPERS
# =====================================================================
def _text_w(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * (font.size // 2 if font else 10)


def _text_h(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[3] - bbox[1]
    except Exception:
        return font.size if font else 20


def _draw_text(draw, x, y, text, font, color, anchor='la'):
    """Draw text with optional anchor. la=left-ascender, ma=middle-ascender, ra=right-ascender."""
    try:
        draw.text((x, y), text, font=font, fill=color, anchor=anchor)
    except Exception:
        # Older PIL doesn't support anchor
        draw.text((x, y), text, font=font, fill=color)


def _draw_centered(draw, x_center, y, text, font, color):
    w = _text_w(draw, text, font)
    draw.text((x_center - w // 2, y), text, font=font, fill=color)


def _draw_right(draw, x_right, y, text, font, color):
    w = _text_w(draw, text, font)
    draw.text((x_right - w, y), text, font=font, fill=color)


def _rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)


# =====================================================================
# BACKGROUND — solid with subtle gradient at edges
# =====================================================================
def _draw_background(img):
    """Charcoal background with subtle vertical gradient."""
    draw = ImageDraw.Draw(img)
    # Solid base
    draw.rectangle([0, 0, CARD_W, CARD_H], fill=COLOR_BG)
    # Subtle gradient at top and bottom (darker)
    for y in range(80):
        alpha = int(40 * (1 - y / 80))
        draw.line([(0, y), (CARD_W, y)], fill=(
            max(0, COLOR_BG[0] - alpha),
            max(0, COLOR_BG[1] - alpha),
            max(0, COLOR_BG[2] - alpha),
        ))
    for y in range(80):
        alpha = int(40 * (1 - y / 80))
        yy = CARD_H - 1 - y
        draw.line([(0, yy), (CARD_W, yy)], fill=(
            max(0, COLOR_BG[0] - alpha),
            max(0, COLOR_BG[1] - alpha),
            max(0, COLOR_BG[2] - alpha),
        ))


# =====================================================================
# TOP STRIP — tier + asset + timestamp
# =====================================================================
def _draw_top_strip(draw, alert):
    """Top strip: tier emoji + asset on left, timestamp on right."""
    strip_h = 80
    # Background slightly darker
    draw.rectangle([0, 0, CARD_W, strip_h], fill=COLOR_BG_TOP)

    tier = alert.get('tier', {'emoji': '🐋', 'name': 'WHALE', 'color': '#FCBF49'})
    asset = alert.get('asset', 'BTC')

    # Left: tier emoji + name + asset
    font_tier = _font(34, 'bold')
    left_text = f"{tier.get('emoji', '🐋')}  {tier.get('name', 'WHALE')}"
    draw.text((40, 22), left_text, font=font_tier, fill=COLOR_GOLD)

    # Asset tag (small box)
    asset_text = asset
    font_asset = _font(28, 'bold')
    asset_w = _text_w(draw, asset_text, font_asset) + 30
    asset_x = 40 + _text_w(draw, left_text, font_tier) + 30
    _rounded_rect(draw, [asset_x, 25, asset_x + asset_w, 25 + 38], radius=8,
                  fill=COLOR_BG_PANEL, outline=COLOR_GOLD_DIM, width=1)
    draw.text((asset_x + 15, 30), asset_text, font=font_asset, fill=COLOR_OFFWHITE)

    # Right: timestamp
    ts = alert.get('timestamp')
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            ts = datetime.now(timezone.utc)
    elif not isinstance(ts, datetime):
        ts = datetime.now(timezone.utc)
    time_str = ts.strftime('%H:%M UTC')
    font_time = _font(28, 'reg')
    _draw_right(draw, CARD_W - 40, 28, time_str, font_time, COLOR_MUTED)


# =====================================================================
# HERO BLOCK — massive USD value
# =====================================================================
def _draw_hero(draw, alert):
    """Hero block: massive USD value with label above."""
    value_usd = alert.get('value_usd', 0)
    crypto_amount = alert.get('crypto_amount', 0)
    asset = alert.get('asset', 'BTC')

    # Label above (small, gold)
    y_label = 130
    font_label = _font(26, 'bold')
    _draw_centered(draw, CARD_W // 2, y_label, "WHALE MOVE DETECTED", font_label, COLOR_GOLD)

    # Big USD value
    if value_usd >= 1_000_000_000:
        hero_text = f"${value_usd/1_000_000_000:.2f}B"
    elif value_usd >= 1_000_000:
        hero_text = f"${value_usd/1_000_000:.2f}M"
    else:
        hero_text = f"${value_usd:,.0f}"

    # Smaller hero font to leave room for crypto amount below
    font_hero = _font(160, 'black')
    hero_y = y_label + 50  # 180
    _draw_centered(draw, CARD_W // 2, hero_y, hero_text, font_hero, COLOR_WHITE)

    # Crypto amount below (mono font for numbers) — well below hero
    crypto_text = f"{crypto_amount:,.4f} {asset}"
    font_crypto = _font(44, 'mono')
    crypto_y = hero_y + 220  # 400 — clear gap from hero (160px font)
    _draw_centered(draw, CARD_W // 2, crypto_y, crypto_text, font_crypto, COLOR_MUTED)


# =====================================================================
# DIRECTION SIDE BAR — colored vertical bar with direction info
# =====================================================================
def _draw_direction_block(draw, alert, y_start):
    """Direction block: colored side bar + label + implication."""
    direction = alert.get('direction', {})
    arrow = direction.get('arrow', '?')
    dir_label = direction.get('label', 'Unknown')
    impl = direction.get('implication', '')
    dir_color_name = direction.get('color', 'gray')

    dir_color = {
        'red': COLOR_BEAR, 'green': COLOR_BULL,
        'yellow': COLOR_WARN, 'gray': COLOR_NEUTRAL,
    }.get(dir_color_name, COLOR_NEUTRAL)

    # Side bar (vertical, colored)
    bar_x = 40
    bar_w = 8
    bar_h = 110
    draw.rectangle([bar_x, y_start, bar_x + bar_w, y_start + bar_h], fill=dir_color)

    # Direction label (large)
    font_dir = _font(40, 'bold')
    dir_text = f"{arrow}  {dir_label}"
    draw.text((bar_x + 25, y_start + 8), dir_text, font=font_dir, fill=dir_color)

    # Implication (smaller, wrapped)
    if impl:
        font_impl = _font(24, 'reg')
        # Truncate to fit
        max_chars = 70
        impl_short = impl if len(impl) <= max_chars else impl[:max_chars - 3] + '...'
        draw.text((bar_x + 25, y_start + 60), impl_short, font=font_impl, fill=COLOR_MUTED)

    return y_start + bar_h + 20


# =====================================================================
# FROM / TO — two-column layout
# =====================================================================
def _draw_from_to(draw, alert, y_start):
    """Two-column From/To block with labels and addresses."""
    from_d = alert.get('from', {})
    to_d = alert.get('to', {})

    col_w = (CARD_W - 80 - 20) // 2  # 40 margin each side, 20 gap
    col1_x = 40
    col2_x = col1_x + col_w + 20

    # Column headers
    font_hdr = _font(22, 'bold')
    draw.text((col1_x, y_start), "FROM", font=font_hdr, fill=COLOR_GOLD)
    draw.text((col2_x, y_start), "TO", font=font_hdr, fill=COLOR_GOLD)

    # Labels (with exchange color)
    font_label = _font(28, 'bold')
    from_label = (from_d.get('label') or 'Unlabeled')[:22]
    to_label = (to_d.get('label') or 'Unlabeled')[:22]

    from_color = COLOR_BULL if from_d.get('is_exchange') else COLOR_OFFWHITE
    to_color = COLOR_BEAR if to_d.get('is_exchange') else COLOR_OFFWHITE

    draw.text((col1_x, y_start + 32), from_label, font=font_label, fill=from_color)
    draw.text((col2_x, y_start + 32), to_label, font=font_label, fill=to_color)

    # Addresses (mono, muted)
    font_addr = _font(22, 'mono')
    draw.text((col1_x, y_start + 70), from_d.get('short', 'Unknown'), font=font_addr, fill=COLOR_MUTED)
    draw.text((col2_x, y_start + 70), to_d.get('short', 'Unknown'), font=font_addr, fill=COLOR_MUTED)

    # Vertical divider between columns
    div_x = col1_x + col_w + 10
    draw.line([(div_x, y_start), (div_x, y_start + 100)], fill=COLOR_DIM, width=1)

    return y_start + 110


# =====================================================================
# SCORE STRIP — whale score with progress bar
# =====================================================================
def _draw_score(draw, alert, y_start):
    """Whale score strip with progress bar."""
    score = alert.get('score', 0)

    # Label on left, score on right
    font_lbl = _font(24, 'bold')
    draw.text((40, y_start), "WHALE SCORE", font=font_lbl, fill=COLOR_GOLD)

    font_score = _font(34, 'bold')
    score_text = f"{score}/100"
    _draw_right(draw, CARD_W - 40, y_start - 4, score_text, font_score,
                COLOR_SCORE_HIGH if score >= 80 else COLOR_SCORE_MID if score >= 60 else COLOR_SCORE_LOW)

    # Progress bar
    bar_y = y_start + 45
    bar_h = 12
    bar_x = 40
    bar_w = CARD_W - 80
    # Background
    _rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=bar_h // 2,
                  fill=COLOR_BG_PANEL)
    # Fill
    fill_w = int(bar_w * (score / 100))
    fill_color = COLOR_SCORE_HIGH if score >= 80 else COLOR_SCORE_MID if score >= 60 else COLOR_SCORE_LOW
    if fill_w > 0:
        _rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=bar_h // 2,
                      fill=fill_color)

    return y_start + 80


# =====================================================================
# PERSONALIZATION — spotted by banner
# =====================================================================
def _draw_personalization(draw, y_start, username=None):
    """Personalization banner. If username: gold banner. Else: subtle placeholder."""
    banner_x = 40
    banner_w = CARD_W - 80
    banner_h = 70

    if username:
        # Gold gradient banner with username
        _rounded_rect(draw, [banner_x, y_start, banner_x + banner_w, y_start + banner_h],
                      radius=12, fill=COLOR_GOLD)
        # Eye icon + text (dark on gold)
        font_spot = _font(32, 'bold')
        spot_text = f"👁  SPOTTED BY  @{username}"
        _draw_centered(draw, CARD_W // 2, y_start + 18, spot_text, font_spot, COLOR_BG_TOP)
    else:
        # Subtle placeholder encouraging personalization
        _rounded_rect(draw, [banner_x, y_start, banner_x + banner_w, y_start + banner_h],
                      radius=12, fill=COLOR_BG_PANEL, outline=COLOR_GOLD_DIM, width=1)
        font_hint = _font(22, 'reg')
        hint_text = "✦  Tap 'Personalize & Share' below to make this card yours  ✦"
        _draw_centered(draw, CARD_W // 2, y_start + 22, hint_text, font_hint, COLOR_DIM)

    return y_start + banner_h + 20


# =====================================================================
# FOOTER GRID — 2x2 grid of CTAs
# =====================================================================
def _draw_footer_grid(draw, y_start):
    """2x2 grid of CTAs: channel + bot handles with descriptions."""
    grid_x = 40
    grid_w = CARD_W - 80
    cell_w = (grid_w - 15) // 2
    cell_h = 75
    gap = 15

    # Background panel for the whole grid
    grid_h = cell_h * 2 + gap
    _rounded_rect(draw, [grid_x, y_start, grid_x + grid_w, y_start + grid_h],
                  radius=14, fill=COLOR_BG_PANEL, outline=COLOR_DIM, width=1)

    # Cell 1: Daily market analysis
    c1_x = grid_x + 12
    c1_y = y_start + 12
    font_cell_label = _font(20, 'bold')
    font_cell_handle = _font(24, 'bold')
    draw.text((c1_x, c1_y), "📊 DAILY ANALYSIS", font=font_cell_label, fill=COLOR_MUTED)
    draw.text((c1_x, c1_y + 28), FOOTER_MAIN_CHANNEL, font=font_cell_handle, fill=COLOR_GOLD)

    # Cell 2: 40+ crypto tools
    c2_x = grid_x + cell_w + gap + 12
    draw.text((c2_x, c1_y), "🛠 40+ CRYPTO TOOLS", font=font_cell_label, fill=COLOR_MUTED)
    draw.text((c2_x, c1_y + 28), FOOTER_MAIN_BOT, font=font_cell_handle, fill=COLOR_GOLD)

    # Divider line between rows
    draw.line([(grid_x + 12, y_start + cell_h + 6),
               (grid_x + grid_w - 12, y_start + cell_h + 6)],
              fill=COLOR_DIM, width=1)

    # Cell 3: Spot & Share
    c3_y = y_start + cell_h + gap + 12
    draw.text((c1_x, c3_y), "🎨 PERSONALIZE", font=font_cell_label, fill=COLOR_MUTED)
    font_cell_hint = _font(20, 'reg')
    draw.text((c1_x, c3_y + 28), "Tap button below", font=font_cell_hint, fill=COLOR_OFFWHITE)

    # Cell 4: Free forever
    draw.text((c2_x, c3_y), "✦ 100% FREE", font=font_cell_label, fill=COLOR_MUTED)
    draw.text((c2_x, c3_y + 28), "No fees, ever", font=font_cell_hint, fill=COLOR_OFFWHITE)

    return y_start + grid_h + 20


# =====================================================================
# SOCIAL ROW — share icons
# =====================================================================
def _draw_social_row(draw, y_start):
    """Three share icons with labels."""
    items = [
        ("🐦", "TWITTER"),
        ("✈", "TELEGRAM"),
        ("📤", "SHARE"),
    ]
    item_w = 200
    total_w = item_w * len(items)
    x_start = (CARD_W - total_w) // 2

    font_icon = _font(42, 'bold')
    font_label = _font(20, 'bold')

    for i, (icon, label) in enumerate(items):
        cx = x_start + i * item_w + item_w // 2
        # Icon
        _draw_centered(draw, cx, y_start, icon, font_icon, COLOR_GOLD)
        # Label
        _draw_centered(draw, cx, y_start + 55, label, font_label, COLOR_MUTED)

    # "TAP TO SHARE" prompt below
    prompt_y = y_start + 95
    font_prompt = _font(20, 'bold')
    _draw_centered(draw, CARD_W // 2, prompt_y, "◆  TAP BUTTONS BELOW TO SHARE  ◆",
                   font_prompt, COLOR_GOLD_DIM)

    return prompt_y + 30


# =====================================================================
# MAIN CARD GENERATOR
# =====================================================================
def generate_alert_card(alert: Dict, username: str = None) -> Optional[str]:
    """
    Generate the MAGAZINE LAYOUT alert card.

    alert dict must have:
      - tier (dict from virality.get_tier)
      - value_usd (float)
      - asset (str)
      - crypto_amount (float)
      - direction (dict from enrichment.infer_direction)
      - from (dict from enrichment.enrich_*)
      - to (dict from enrichment.enrich_*)
      - score (int 0-100)
      - tx_id (str)
      - timestamp (datetime or ISO str)

    username (optional): if provided, adds "SPOTTED BY @username" banner

    Returns: file path or None on failure.
    """
    if not PIL_AVAILABLE:
        return None

    try:
        img = Image.new('RGB', (CARD_W, CARD_H), COLOR_BG)
        _draw_background(img)
        draw = ImageDraw.Draw(img)

        # Layout (top to bottom):
        # 1. Top strip (0-80)
        _draw_top_strip(draw, alert)

        # 2. Hero block (130-470)
        _draw_hero(draw, alert)

        # 3. Direction block (490-620)
        y = 510
        y = _draw_direction_block(draw, alert, y)

        # 4. From/To (640-750)
        y = _draw_from_to(draw, alert, y + 10)

        # 5. Score (770-850)
        y = _draw_score(draw, alert, y + 10)

        # 6. Personalization (870-960)
        y = _draw_personalization(draw, y + 10, username=username)

        # 7. Footer grid (980-1130)
        y = _draw_footer_grid(draw, y + 10)

        # 8. Social row (1150-1280)
        _draw_social_row(draw, y + 10)

        # Save
        suffix = f"_{username}" if username else ""
        out_path = CARDS_DIR / f"alert_{alert.get('tx_id', 'x')[:16]}{suffix}.png"
        img.save(out_path, 'PNG', optimize=True)
        log.info(f"Magazine card generated: {out_path}")
        return str(out_path)

    except Exception as e:
        log.warning(f"Card generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# =====================================================================
# SUMMARY CARD (daily digest)
# =====================================================================
# def generate_summary_card(stats: dict) -> Optional[str]:
#     """Generate a magazine-style daily summary card."""
#     if not PIL_AVAILABLE:
#         return None

#     try:
#         img = Image.new('RGB', (CARD_W, CARD_H), COLOR_BG)
#         _draw_background(img)
#         draw = ImageDraw.Draw(img)

#         # Top strip
#         draw.rectangle([0, 0, CARD_W, 80], fill=COLOR_BG_TOP)
#         font_top = _font(34, 'bold')
#         _draw_centered(draw, CARD_W // 2, 22, "📊  DAILY DIGEST", font_top, COLOR_GOLD)

#         # Date
#         date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
#         font_date = _font(28, 'reg')
#         _draw_centered(draw, CARD_W // 2, 110, date_str, font_date, COLOR_MUTED)

#         # Big number
#         total = stats.get('total_alerts', 0)
#         font_big = _font(200, 'black')
#         _draw_centered(draw, CARD_W // 2, 160, str(total), font_big, COLOR_WHITE)

#         font_lbl = _font(32, 'bold')
#         _draw_centered(draw, CARD_W // 2, 380, "WHALE ALERTS TODAY", font_lbl, COLOR_GOLD)

#         # Breakdown
#         font_stat = _font(38, 'bold')
#         y = 460
#         for label, color in [
#             (f"BTC:  {stats.get('btc_count', 0)}", COLOR_GOLD),
#             (f"ETH:  {stats.get('eth_count', 0)}", COLOR_OFFWHITE),
#             (f"Stables:  {stats.get('stable_count', 0)}", COLOR_BULL),
#         ]:
#             _draw_centered(draw, CARD_W // 2, y, label, font_stat, color)
#             y += 50

#         # Total volume
#         total_usd = stats.get('total_usd', 0)
#         if total_usd >= 1_000_000_000:
#             vol_text = f"Total volume: ${total_usd/1_000_000_000:.2f}B"
#         elif total_usd >= 1_000_000:
#             vol_text = f"Total volume: ${total_usd/1_000_000:.2f}M"
#         else:
#             vol_text = f"Total volume: ${total_usd:,.0f}"
#         font_vol = _font(30, 'bold')
#         _draw_centered(draw, CARD_W // 2, y + 20, vol_text, font_vol, COLOR_OFFWHITE)

#         # Net flow
#         net_flow = stats.get('net_flow', 0)
#         if net_flow > 0:
#             flow_text = f"↗ Net inflow: +${abs(net_flow)/1_000_000:.2f}M (bearish)"
#             flow_color = COLOR_BEAR
#         elif net_flow < 0:
#             flow_text = f"↘ Net outflow: -${abs(net_flow)/1_000_000:.2f}M (bullish)"
#             flow_color = COLOR_BULL
#         else:
#             flow_text = "Net flow: neutral"
#             flow_color = COLOR_NEUTRAL
#         font_flow = _font(24, 'bold')
#         _draw_centered(draw, CARD_W // 2, y + 70, flow_text, font_flow, flow_color)

#         # Footer + social
#         y = _draw_footer_grid(draw, y + 130)
#         _draw_social_row(draw, y + 10)

#         out_path = CARDS_DIR / f"summary_{date_str}.png"
#         img.save(out_path, 'PNG', optimize=True)
#         return str(out_path)
#     except Exception as e:
#         log.warning(f"Summary card generation failed: {e}")
#         return None


# =====================================================================
# WEEKLY WINNER CARD
# =====================================================================
def generate_weekly_winner_card(winner: Dict, runner_ups: list = None) -> Optional[str]:
    """Generate the 'Whale of the Week' card — magazine layout."""
    if not PIL_AVAILABLE:
        return None

    try:
        img = Image.new('RGB', (CARD_W, CARD_H), COLOR_BG)
        _draw_background(img)
        draw = ImageDraw.Draw(img)

        # Top strip
        draw.rectangle([0, 0, CARD_W, 80], fill=COLOR_BG_TOP)
        font_top = _font(34, 'bold')
        _draw_centered(draw, CARD_W // 2, 22, "🏆  WHALE OF THE WEEK", font_top, COLOR_GOLD)

        # Date range
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        date_range = f"{week_ago.strftime('%b %d')} — {now.strftime('%b %d, %Y')}"
        font_date = _font(26, 'reg')
        _draw_centered(draw, CARD_W // 2, 105, date_range, font_date, COLOR_MUTED)

        # Hero value
        value_usd = winner.get('value_usd', 0)
        if value_usd >= 1_000_000_000:
            hero_text = f"${value_usd/1_000_000_000:.2f}B"
        elif value_usd >= 1_000_000:
            hero_text = f"${value_usd/1_000_000:.2f}M"
        else:
            hero_text = f"${value_usd:,.0f}"
        font_hero = _font(180, 'black')
        _draw_centered(draw, CARD_W // 2, 160, hero_text, font_hero, COLOR_WHITE)

        # Asset + score
        asset = winner.get('asset', '?')
        font_sub = _font(38, 'bold')
        sub_text = f"{asset}  •  Score: {winner.get('score', 0)}/100"
        _draw_centered(draw, CARD_W // 2, 380, sub_text, font_sub, COLOR_GOLD)

        # Direction
        dir_label = winner.get('direction_label', '')
        if dir_label:
            font_dir = _font(28, 'reg')
            _draw_centered(draw, CARD_W // 2, 440, dir_label, font_dir, COLOR_MUTED)

        # From/To
        y = _draw_from_to(draw, {
            'from': {'label': winner.get('from_label', 'Unlabeled'), 'short': '', 'is_exchange': False},
            'to': {'label': winner.get('to_label', 'Unlabeled'), 'short': '', 'is_exchange': False},
        }, 510)

        # Runner-ups
        if runner_ups:
            font_runner_title = _font(24, 'bold')
            _draw_centered(draw, CARD_W // 2, y + 20, "OTHER NOTABLE MOVES THIS WEEK",
                           font_runner_title, COLOR_GOLD)
            font_runner = _font(28, 'bold')
            ry = y + 60
            for i, ru in enumerate(runner_ups[:4], 1):
                ru_usd = ru.get('value_usd', 0)
                if ru_usd >= 1_000_000:
                    ru_text_val = f"${ru_usd/1_000_000:.1f}M"
                else:
                    ru_text_val = f"${ru_usd:,.0f}"
                ru_asset = ru.get('asset', '?')
                line = f"{i}. {ru_text_val}  {ru_asset}"
                _draw_centered(draw, CARD_W // 2, ry, line, font_runner, COLOR_OFFWHITE)
                ry += 38

        # Footer + social
        y_final = _draw_footer_grid(draw, 980)
        _draw_social_row(draw, y_final + 10)

        date_str = now.strftime('%Y_%W')
        out_path = CARDS_DIR / f"weekly_{date_str}.png"
        img.save(out_path, 'PNG', optimize=True)
        log.info(f"Magazine weekly card generated: {out_path}")
        return str(out_path)
    except Exception as e:
        log.warning(f"Weekly card generation failed: {e}")
        return None
