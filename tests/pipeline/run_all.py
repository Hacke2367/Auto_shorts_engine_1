import importlib
import traceback
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Running this file directly puts tests/pipeline/ on sys.path, not the repo root,
# so the `tests.pipeline.*` imports below would fail. Put the root on the path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    test_dir = Path(__file__).resolve().parent
    test_files = [f.stem for f in test_dir.glob("test_*.py") if f.is_file()]
    
    results = {}
    
    for mod_name in sorted(test_files):
        try:
            mod = importlib.import_module(f"tests.pipeline.{mod_name}")
            print(f"\n[{mod_name}] Starting...")
            if hasattr(mod, "run_tests"):
                # All tests cleanly return True on success or throw Exceptions
                status = mod.run_tests()
                results[mod_name] = "PASS" if status else "FAIL"
            else:
                results[mod_name] = "SKIPPED (no run_tests() found)"
        except Exception as e:
            print(f"[{mod_name}] ❌ CRASH: {e}")
            traceback.print_exc()
            results[mod_name] = "FAIL"
            
    print("\n" + "=" * 40)
    print("PIPELINE TEST SUMMARY")
    print("=" * 40)
    
    fails = 0
    for name, status in results.items():
        icon = "✅" if status == "PASS" else ("❌" if "FAIL" in status else "⚠️")
        if "FAIL" in status:
            fails += 1
        print(f"{icon} {name.ljust(40)} {status}")
        
    print("=" * 40)
    if fails > 0:
        print(f"❌ {fails} tests failed!")
        sys.exit(1)
    else:
        print("✅ ALL PIPELINE TESTS PASSED!")
        sys.exit(0)

if __name__ == "__main__":
    main()
