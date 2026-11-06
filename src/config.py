from manim import *
import os

"""
PROJECT CONFIGURATION (The Brain) - VERSION 3.0 (Final Locked)
Contains:
1. Video Settings (9:16)
2. Color Palette (Neon + Spy Brand)
3. Directory Paths
"""

# ----------------------------------------
# 1. VIDEO SETTINGS (YouTube Shorts - 9:16)
# ----------------------------------------
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
BACKGROUND_COLOR = "#070B14"

# Manim Global Config
config.pixel_height = VIDEO_HEIGHT
config.pixel_width = VIDEO_WIDTH
config.frame_height = 16.0
config.frame_width = 9.0
config.background_color = BACKGROUND_COLOR


# ----------------------------------------
# 2. COLOR PALETTE (BigData Leak Theme)
# ----------------------------------------
class Theme:
    # --- CORE BRANDING (Spy/Hacker Theme) ---
    BACKGROUND = "#070B14"  # Deep navy (finance terminal), not pitch black
    BRAND_CYAN = "#38BDF8"  # Primary accent (sky blue; was neon cyan)
    BRAND_RED = "#FF4D6D"  # Secondary accent (rose; was neon magenta)
    BRAND_WHITE = "#FFFFFF"

    # --- TEXT COLORS ---
    TEXT_MAIN = "#FFFFFF"  # Headers / Values
    TEXT_SUB = "#AEB7C2"  # Labels / Subtitles (cool premium grey; unified w/ utils fallback)
    TEXT_DIM = "#555555"  # Grid numbers / Less visible text

    # --- NEON ACCENTS (For Graphs) ---
    NEON_BLUE = "#38BDF8"  # Blue accent (finance skin 2026-11; was neon cyan)
    NEON_PINK = "#FF4D6D"  # Rose accent (was neon magenta)
    NEON_GREEN = "#22C55E"  # Up / profit
    NEON_PURPLE = "#BD00FF"  # Royal / Mystery
    NEON_YELLOW = "#FFC74A"  # Warning / Gold (richer amber-gold; was harsh #FFFF00)
    NEON_ORANGE = "#FF9900"  # Secondary Highlight

    # --- MULTI-COLOR PALETTE (For Donut/Sort Charts) ---
    # Use this list when you need multiple distinct colors
    PALETTE_MAIN = [NEON_BLUE, NEON_PURPLE, NEON_PINK, NEON_GREEN, NEON_YELLOW, NEON_ORANGE]

    # --- CHART SPECIFIC (Bar Chart / Line Chart) ---
    C_CONTAINER_FILL = "#050505"
    C_CONTAINER_STROKE = "#1E3A5F"  # Navy border

    # Gradient for Bars
    C_BAR_GRADIENT = ["#1D4ED8", "#38BDF8", "#BAE6FD"]

    # Laser/Dot Logic
    C_DOT_CORE = "#FFFFFF"
    C_DOT_GLOW = "#38BDF8"
    C_LINE_CORE = "#FFFFFF"
    C_LINE_GLOW = "#38BDF8"

    # --- UTILITY COLORS ---
    BAR_FILL = "#1F1F1F"  # Empty slot background
    AXIS_COLOR = "#333333"  # Grid lines (Subtle)

    # --- STATUS / VS MODE COLORS ---
    PROFIT = "#22C55E"  # Green (up)
    LOSS = "#EF4444"  # Red (down)

    GOLD = "#FFD700"  # Rank 1 / Winner
    SILVER = "#C0C0C0"  # Rank 2
    BRONZE = "#CD7F32"  # Rank 3

    PLAYER_1 = NEON_BLUE  # Default P1
    PLAYER_2 = NEON_YELLOW  # Default P2 (gold vs blue reads finance, not gaming)


# ----------------------------------------
# 2b. BRAND + INTRO (finance skin, 2026-11)
# ----------------------------------------
BRAND_NAME = "BIGDATA LEAK"   # shown top-left on every frame; rename here only
BRAND_HANDLE = ""             # e.g. "@bigdataleak"; empty -> watermark shows BRAND_NAME
INTRO_ENABLED = False         # hook-first: no black brand card before the title

# ----------------------------------------
# 3. DIRECTORIES (Folder Paths)
# ----------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ----------------------------------------
# 3b. FONT REGISTRATION (bundle -> guarantee resolution regardless of OS install)
# ----------------------------------------
# Register the bundled TTFs with Pango so font="Montserrat" ALWAYS resolves to
# our shipped files, even on machines where Montserrat isn't OS-installed
# (otherwise Manim silently falls back to a default face). Fully fail-safe: any
# registration error degrades to the current behaviour and never breaks a render.
try:
    import manimpango as _manimpango
    for _font_file in ("Montserrat-Regular.ttf", "Montserrat-Bold.ttf",
                       "SpaceGrotesk-Bold.ttf", "Anton-Regular.ttf"):
        _font_path = os.path.join(FONTS_DIR, _font_file)
        if os.path.exists(_font_path):
            try:
                _manimpango.register_font(_font_path)
            except Exception:
                pass
except Exception:
    pass

# ----------------------------------------
# 3c. SMALL-TEXT KERNING FIX
# ----------------------------------------
# Pango lays glyphs out at the requested size, and at small sizes it rounds each
# advance to whole units -- captions/HUD/labels came out as "B REAKDOWN",
# "CON FIDEN TIAL", "t onn es". Laying small Text out at a large size and scaling the
# result down keeps the spacing true. The public font_size still reads back as the
# requested size (it is derived from height / initial_height). Patched on the class,
# so every template's `from manim import *` Text picks it up.
_TEXT_MIN_LAYOUT_SIZE = 48.0
try:
    from manim.mobject.text.text_mobject import Text as _ManimText

    if not getattr(_ManimText, "_autoshorts_kerning_patch", False):
        _orig_text_init = _ManimText.__init__

        def _text_init_large_layout(self, text, *args, font_size=DEFAULT_FONT_SIZE, **kwargs):
            requested = float(font_size)
            if 0.0 < requested < _TEXT_MIN_LAYOUT_SIZE:
                _orig_text_init(self, text, *args, font_size=_TEXT_MIN_LAYOUT_SIZE, **kwargs)
                self.scale(requested / _TEXT_MIN_LAYOUT_SIZE)
            else:
                _orig_text_init(self, text, *args, font_size=font_size, **kwargs)

        _ManimText.__init__ = _text_init_large_layout
        _ManimText._autoshorts_kerning_patch = True
except Exception:
    pass

# Premium display face for hero/titles (body text stays Montserrat). Resolve to
# the bundled display font only if it actually registered; otherwise fall back to
# Montserrat so a missing/failed TTF can NEVER break a render.
try:
    FONT_DISPLAY = "Space Grotesk" if any(
        "Space Grotesk" in _f for _f in _manimpango.list_fonts()
    ) else "Montserrat"
except Exception:
    FONT_DISPLAY = "Montserrat"

# -----------------------------------------
# map setting

MAP_DEFAULT_METRIC = "VALUE"
MAP_DEFAULT_UNIT = ""   # if missing -> show only number
MAP_MAX_CARDS = 10

# --- MAP / GEO TEMPLATE SETTINGS ---
GROUP_COLORS = {
    "West": Theme.NEON_BLUE,
    "Asia": Theme.NEON_PINK,
    "East": Theme.NEON_GREEN,
    "Europe": Theme.NEON_PURPLE,
    "Africa": Theme.NEON_YELLOW,
    "LatAm": Theme.NEON_ORANGE,
}



# ----------------------------------------
# 4. FONT SETTINGS
# ----------------------------------------
DEFAULT_FONT = "DejaVu Sans"
# Note: Manim uses 'font="Montserrat"' in calls, ensure it's installed or fallback to Arial.