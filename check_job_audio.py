import json
import sys
from pathlib import Path

def norm_key(s: str) -> str:
    s = str(s).strip().lower().replace("-", "_").replace(" ", "_")
    if s.startswith("item") and s.replace("_","").startswith("item"):
        import re
        m = re.match(r"^item_?(\d+)$", s)
        if m:
            return f"item_{int(m.group(1))}"
    return s

job_dir = Path(sys.argv[1]).resolve()
job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))

audio = job.get("audio", {})
print("audio type:", type(audio))
print("audio keys:", list(audio.keys()) if isinstance(audio, dict) else None)

segs = audio.get("segments") if isinstance(audio, dict) else None
print("segments type:", type(segs))
print("segments len:", len(segs) if isinstance(segs, list) else None)

if not isinstance(segs, list) or not segs:
    print("❌ segments missing/empty -> main.py will skip mux")
    sys.exit(0)

print("\n--- segments resolved paths ---")
seg_map = {}
for s in segs:
    name = norm_key(s.get("name",""))
    path = s.get("path","")
    p = (job_dir / path).resolve()
    seg_map[name] = p
    print(name, "=>", p, "| exists:", p.exists())

order = audio.get("order", [])
print("\n--- order check ---")
for k in order:
    nk = norm_key(k)
    print(k, "->", nk, "| found:", nk in seg_map)
