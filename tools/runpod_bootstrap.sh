#!/usr/bin/env bash
#
# runpod_bootstrap.sh - one-time setup of the RunPod network volume.
#
# Run this ONCE, on a pod with the network volume mounted at /workspace. Every
# later pod that mounts the same volume boots render-ready in seconds: no image
# build, no registry, no pip install.
#
# Everything it creates lives under /workspace (the persistent volume). Nothing
# is written to the container filesystem, which is thrown away when the pod is
# terminated - except the font cache, which is rebuilt per pod by
# runpod_render.ps1.
#
#   ssh root@<pod> 'bash -s' < tools/runpod_bootstrap.sh
#
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
VENV="$WORKSPACE/venv"
REPO="$WORKSPACE/repo"
FONTS="$WORKSPACE/fonts"

echo "=== [1/5] system packages ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Cairo + Pango are what Manim rasterizes and shapes text with; ffmpeg is the
# whole audio/mux half of main.py; fontconfig is how Pango finds our fonts.
apt-get install -y -qq --no-install-recommends \
    ffmpeg \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgirepository-1.0-1 \
    fontconfig \
    python3 \
    python3-pip \
    python3-venv \
    rsync \
    tar
# pycairo and ManimPango publish wheels for common CPython versions, but if
# the pod's base image ships a python they have no wheel for, pip silently
# falls back to building from source - which needs headers, not just the
# runtime libs above. Installing them here turns a confusing mid-bootstrap
# failure into a non-event. Costs ~90s, once per volume.
apt-get install -y -qq --no-install-recommends build-essential pkg-config python3-dev libcairo2-dev libpango1.0-dev

echo "=== [2/5] python venv at $VENV ==="
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip

echo "=== [3/5] python deps ==="
# requirements-render.txt is EXACTLY pinned to the laptop's versions. The
# full requirements.txt is deliberately NOT used here: it is unpinned
# (manim>=0.18.0), so it would install whatever is newest and drift the
# cloud render away from the local one - and it drags in the Phase 1-3
# stack that this pod never runs.
if [ -f "$REPO/requirements-render.txt" ]; then
    "$VENV/bin/pip" install --quiet -r "$REPO/requirements-render.txt"
else
    echo "  ERROR: $REPO/requirements-render.txt not found."
    echo "  Push the code bundle first (runpod_render.ps1 sends it), then re-run."
    exit 1
fi

echo "=== [4/5] fonts ==="
mkdir -p "$FONTS" /root/.fonts
if compgen -G "$FONTS/*.ttf" > /dev/null; then
    cp -f "$FONTS"/*.ttf /root/.fonts/
fi
fc-cache -f > /dev/null 2>&1 || true

echo "=== [5/5] verification ==="
fail=0

"$VENV/bin/python" - <<'PYCHECK' || fail=1
import sys
try:
    import manim, cairo, numpy
    print("  manim  ", manim.__version__, "(laptop: 0.19.1)")
    print("  pycairo", cairo.version, "(laptop: 1.29.0)")
    print("  numpy  ", numpy.__version__, "(laptop: 2.2.6)")
    py = sys.version.split()[0]
    print("  python ", py, "(laptop: 3.10.11)")
    if not py.startswith(("3.10.", "3.11.", "3.12.")):
        print("  WARNING: untested python for these pins - eyeball the first render.")
except Exception as e:
    print("  IMPORT FAILED:", e)
    raise SystemExit(1)
PYCHECK

if ! command -v ffmpeg > /dev/null; then
    echo "  ffmpeg  MISSING"
    fail=1
else
    echo "  ffmpeg  $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
fi

# Font parity is the single biggest source of "cloud output looks different".
# Fail loudly here rather than discovering it in a rendered video.
for family in Consolas "Segoe UI" Montserrat Anton "Space Grotesk"; do
    if fc-list | grep -qi "$family"; then
        echo "  font    OK      $family"
    else
        echo "  font    MISSING $family"
        fail=1
    fi
done

echo ""
if [ "$fail" -ne 0 ]; then
    echo "BOOTSTRAP INCOMPLETE - fix the MISSING lines above before rendering."
    echo "Fonts live in $FONTS (push them with: runpod_render.ps1 -SyncAssets)."
    exit 1
fi

echo "Bootstrap OK. Volume is render-ready."
echo "  venv: $VENV/bin/python"
echo "  repo: $REPO"
