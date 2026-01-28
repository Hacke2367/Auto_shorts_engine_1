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
BACKGROUND_COLOR = "#0A0A0A"

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
    BACKGROUND = "#050505"  # Deepest Dark (Not Pitch Black)
    BRAND_CYAN = "#00F0FF"  # Primary Brand Color (Data)
    BRAND_RED = "#FF0055"  # Secondary Brand Color (Alert/REC)
    BRAND_WHITE = "#FFFFFF"

    # --- TEXT COLORS ---
    TEXT_MAIN = "#FFFFFF"  # Headers / Values
    TEXT_SUB = "#CCCCCC"  # Labels / Subtitles
    TEXT_DIM = "#555555"  # Grid numbers / Less visible text

    # --- NEON ACCENTS (For Graphs) ---
    NEON_BLUE = "#00F0FF"  # Tech
    NEON_PINK = "#FF0055"  # Aggressive
    NEON_GREEN = "#00FF66"  # Success / Money
    NEON_PURPLE = "#BD00FF"  # Royal / Mystery
    NEON_YELLOW = "#FFFF00"  # Warning / Gold substitute
    NEON_ORANGE = "#FF9900"  # Secondary Highlight

    # --- MULTI-COLOR PALETTE (For Donut/Sort Charts) ---
    # Use this list when you need multiple distinct colors
    PALETTE_MAIN = [NEON_BLUE, NEON_PURPLE, NEON_PINK, NEON_GREEN, NEON_YELLOW, NEON_ORANGE]

    # --- CHART SPECIFIC (Bar Chart / Line Chart) ---
    C_CONTAINER_FILL = "#050505"
    C_CONTAINER_STROKE = "#004488"  # Dark Blue Border

    # Gradient for Bars
    C_BAR_GRADIENT = ["#0033CC", "#0088FF", "#00FFFF"]

    # Laser/Dot Logic
    C_DOT_CORE = "#FFFFFF"
    C_DOT_GLOW = "#00FFFF"
    C_LINE_CORE = "#FFFFFF"
    C_LINE_GLOW = "#00FFFF"

    # --- UTILITY COLORS ---
    BAR_FILL = "#1F1F1F"  # Empty slot background
    AXIS_COLOR = "#333333"  # Grid lines (Subtle)

    # --- STATUS / VS MODE COLORS ---
    PROFIT = "#00FF66"  # Green
    LOSS = "#FF0055"  # Red

    GOLD = "#FFD700"  # Rank 1 / Winner
    SILVER = "#C0C0C0"  # Rank 2
    BRONZE = "#CD7F32"  # Rank 3

    PLAYER_1 = NEON_BLUE  # Default P1
    PLAYER_2 = NEON_PINK  # Default P2


# ----------------------------------------
# 3. DIRECTORIES (Folder Paths)
# ----------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

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
DEFAULT_FONT = "Arial"
# Note: Manim uses 'font="Montserrat"' in calls, ensure it's installed or fallback to Arial.