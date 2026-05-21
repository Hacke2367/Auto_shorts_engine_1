from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from src.agents.core.job_manager import JobManager

def close_logger(jm: JobManager):
    """Force close log files so Windows allows folder deletion."""
    if jm._logger:
        for handler in jm._logger.handlers[:]:
            handler.close()
            jm._logger.removeHandler(handler)

def test_manual_initialize_creates_standard_dirs():
    with TemporaryDirectory() as tmpdir:
        jm = JobManager(template_name="vs_card", jobs_root=Path(tmpdir))
        jm.initialize()
        assert jm.job_dir.exists()
        assert jm.data_dir.exists()
        assert jm.audio_dir.exists()
        assert jm.script_dir.exists()
        assert jm.output_dir.exists()
        close_logger(jm)

def test_auto_initialize_creates_auto_dirs():
    with TemporaryDirectory() as tmpdir:
        jm = JobManager(template_name="auto", jobs_root=Path(tmpdir))
        jm.initialize()
        assert jm.job_dir.exists()
        assert jm.discovery_dir.exists()
        assert jm.attempts_dir.exists()
        close_logger(jm)

def test_mark_step_and_get_metadata():
    with TemporaryDirectory() as tmpdir:
        jm = JobManager(template_name="vs_card", jobs_root=Path(tmpdir))
        jm.initialize()
        jm.mark_step_completed("phase1_discovery", {"rows": 6, "template": "vs_card"})
        assert jm.is_step_completed("phase1_discovery") is True
        meta = jm.get_step_metadata("phase1_discovery")
        assert meta is not None
        assert meta["rows"] == 6
        assert meta["template"] == "vs_card"
        close_logger(jm)

def test_corrupt_state_returns_false_not_crash():
    with TemporaryDirectory() as tmpdir:
        jm = JobManager(template_name="vs_card", jobs_root=Path(tmpdir))
        jm.initialize()
        state_file = jm.job_dir / ".pipeline_state.json"
        state_file.write_text("{bad json", encoding="utf-8")
        assert jm.is_step_completed("phase1_discovery") is False
        close_logger(jm)

def test_set_template_allowed_only_in_auto_mode():
    with TemporaryDirectory() as tmpdir:
        auto_jm = JobManager(template_name="auto", jobs_root=Path(tmpdir))
        auto_jm.initialize()
        auto_jm.set_template("vs_card")
        assert auto_jm.template_name == "vs_card"
        close_logger(auto_jm)

        manual_jm = JobManager(template_name="vs_card", jobs_root=Path(tmpdir))
        manual_jm.initialize()
        try:
            manual_jm.set_template("bar_chart")
            raise AssertionError("Expected RuntimeError in manual mode")
        except RuntimeError:
            pass
        finally:
            close_logger(manual_jm)

def test_get_attempt_dir_only_auto_mode():
    with TemporaryDirectory() as tmpdir:
        auto_jm = JobManager(template_name="auto", jobs_root=Path(tmpdir))
        auto_jm.initialize()
        attempt_dir = auto_jm.get_attempt_dir("vs_card", 1)
        assert attempt_dir.exists()
        assert "01_vs_card" in attempt_dir.name
        close_logger(auto_jm)

        manual_jm = JobManager(template_name="vs_card", jobs_root=Path(tmpdir))
        manual_jm.initialize()
        try:
            manual_jm.get_attempt_dir("vs_card", 1)
            raise AssertionError("Expected RuntimeError for manual mode")
        except RuntimeError:
            pass
        finally:
            close_logger(manual_jm)

def main():
    tests = [
        test_manual_initialize_creates_standard_dirs,
        test_auto_initialize_creates_auto_dirs,
        test_mark_step_and_get_metadata,
        test_corrupt_state_returns_false_not_crash,
        test_set_template_allowed_only_in_auto_mode,
        test_get_attempt_dir_only_auto_mode,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} -> {e}")
            failed += 1

    print(f"\nSUMMARY: passed={passed}, failed={failed}")

    if failed > 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()