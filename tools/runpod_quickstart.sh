#!/usr/bin/env bash
# runpod_quickstart.sh - everything the pod needs, in one command.
#
# Runs INSIDE the pod's web terminal, from the unpacked bundle directory:
#
#     bash tools/runpod_quickstart.sh
#
# Installs system libs, builds the venv, installs the PINNED render deps,
# installs the fonts, and verifies all of it. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="/workspace/venv"

echo "=== [1/4] system packages (~2 min) ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    ffmpeg libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgirepository-1.0-1 fontconfig python3 python3-pip python3-venv tar
# Headers, in case pip has no wheel for this image's python and has to build.
apt-get install -y -qq --no-install-recommends \
    build-essential pkg-config python3-dev libcairo2-dev libpango1.0-dev

echo "=== [2/4] fonts ==="
mkdir -p /root/.fonts
# Windows faces (Consolas/Segoe UI/Arial) + the repo's OFL faces travel in the
# bundle; Linux has none of them and Pango would silently substitute.
cp -f "$HERE"/.fonts_stage/*.ttf /root/.fonts/ 2>/dev/null || true
cp -f "$HERE"/assets/fonts/*.ttf /root/.fonts/ 2>/dev/null || true
fc-cache -f > /dev/null 2>&1 || true

echo "=== [3/4] python + deps (~4 min) ==="
# Some RunPod images are Ubuntu 20.04, where `python3` is 3.8 - too old for
# manim 0.19 (needs >=3.9), and pip just reports "no matching distribution".
# Pull 3.10 from deadsnakes in that case: it matches the laptop exactly.
PY=python3
if ! python3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,9) else 1)" 2>/dev/null; then
    echo "  image ships $(python3 -V 2>&1) - installing python3.10"
    apt-get install -y -qq software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq python3.10 python3.10-venv python3.10-dev
    PY=python3.10
fi
# A venv built by the wrong interpreter stays wrong - rebuild it.
if [ -x "$VENV/bin/python" ] && ! "$VENV/bin/python" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,9) else 1)" 2>/dev/null; then
    echo "  existing venv is too old - rebuilding"
    rm -rf "$VENV"
fi
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$HERE/requirements-render.txt"

echo "=== [4/4] verification ==="
fail=0
"$VENV/bin/python" - <<'PYCHECK' || fail=1
import sys
import manim, cairo, numpy
print("  manim  ", manim.__version__, "(laptop: 0.19.1)")
print("  pycairo", cairo.version, "(laptop: 1.29.0)")
py = sys.version.split()[0]
print("  python ", py, "(laptop: 3.10.11)")
if not py.startswith(("3.10.", "3.11.", "3.12.")):
    print("  WARNING: untested python for these pins - eyeball the first render.")
PYCHECK

command -v ffmpeg > /dev/null && echo "  ffmpeg  OK" || { echo "  ffmpeg  MISSING"; fail=1; }

# Font parity is the #1 cause of "cloud video looks different". Fail here, not
# 8 minutes into a render.
for family in Consolas "Segoe UI" Montserrat Anton "Space Grotesk"; do
    if fc-list | grep -qi "$family"; then echo "  font    OK      $family"
    else echo "  font    MISSING $family"; fail=1; fi
done

echo ""
if [ "$fail" -ne 0 ]; then
    echo "SETUP INCOMPLETE - fix the MISSING lines above before rendering."
    exit 1
fi
echo "Setup OK. Render with:"
echo "  $VENV/bin/python render_batch.py --jobs jobs/scan_job -q m --force"
