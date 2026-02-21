import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from audio_duration import main


if __name__ == "__main__":
    raise SystemExit(main())
