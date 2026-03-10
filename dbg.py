import sys, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
try:
    from tests.pipeline.test_cli_repair_loop_no_llm import run_tests
    run_tests()
except Exception:
    traceback.print_exc()
