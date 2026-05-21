from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.phase1_discovery.archive_manager import ArchiveManager
from src.agents.core.models import QueuedTopic

def get_test_archive(tmpdir: str) -> ArchiveManager:
    """Helper to give a valid file path inside the temp directory."""
    file_path = Path(tmpdir) / "test_archive.json"
    return ArchiveManager(file_path)

def create_dummy_queue_topic(topic_name: str) -> QueuedTopic:
    """Helper to satisfy Pydantic strict requirements."""
    return QueuedTopic(
        topic=topic_name,
        normalized_topic=ArchiveManager.normalize_topic(topic_name),
        best_fit_template="bar_chart",
        final_score=8.5,
        fit_reason="good topic, save for later"
    )

def test_archive_initializes():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        assert archive is not None

def test_mark_produced_creates_duplicate_memory():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        topic = "nvidia vs amd revenue race"
        archive.mark_produced(topic, reason="used in video")
        assert archive.is_duplicate(topic) is True

def test_mark_rejected_creates_duplicate_memory():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        topic = "top 10 technical giants"
        archive.mark_rejected(topic, reason="too generic")
        assert archive.is_duplicate(topic) is True

def test_add_to_queue_persists():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        queued = create_dummy_queue_topic("smartphone brands losing market share")
        archive.add_to_queue(queued)

        queue = archive.get_queue()  # FIXED method name
        assert len(queue) >= 1
        assert any("smartphone brands losing market share" in q.topic for q in queue)

def test_queue_duplicate_handling_basic():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        queued = create_dummy_queue_topic("smartphone brands losing market share")
        
        archive.add_to_queue(queued)
        archive.add_to_queue(queued) # Duplicate add attempt

        queue = archive.get_queue()  # FIXED method name
        assert len(queue) == 1 # Archive manager should dedupe this

def test_archive_files_are_written():
    with TemporaryDirectory() as tmpdir:
        archive = get_test_archive(tmpdir)
        archive.mark_produced("nvidia vs amd revenue race", reason="used")
        archive.mark_rejected("top 10 technical giants", reason="generic")
        
        archive.add_to_queue(create_dummy_queue_topic("smartphone brands losing market share"))

        files = list(Path(tmpdir).glob("*.json"))
        assert len(files) > 0, "Expected archive json files to be created"

def main():
    tests = [
        test_archive_initializes,
        test_mark_produced_creates_duplicate_memory,
        test_mark_rejected_creates_duplicate_memory,
        test_add_to_queue_persists,
        test_queue_duplicate_handling_basic,
        test_archive_files_are_written,
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