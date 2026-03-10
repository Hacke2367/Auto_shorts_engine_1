import tempfile
import json
import logging
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.phase2_scripting.dummy_phase1_outputs import get_dummy_dataset
from tests.phase2_scripting.fake_llm import (
    build_fake_monologue, build_bad_monologue_missing_tag,
    build_bad_monologue_unknown_tag, build_bad_monologue_too_short
)

from src.agents.phase2_scripting.timing import build_segment_plan
from src.agents.phase2_scripting.xml_parser import parse_monologue
from src.agents.phase2_scripting.contracts import ScriptParsingError
from src.agents.phase2_scripting.llm_writer import _get_failing_segments
from src.agents.core.job_manager import JobManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_timing_and_parsing():
    logger.info("--- Testing Offline Timing & Parsing ---")
    dataset_n3 = get_dummy_dataset(num_rows=3)
    dataset_n6 = get_dummy_dataset(num_rows=6)
    
    logger.info("Testing dynamic expansion N=3 for 'bar_chart'")
    plan_n3 = build_segment_plan("job_123", "bar_chart", "savage_roast_master", dataset_n3)
    assert len(plan_n3.segments) == 7, "Expected 7 total segments (HOOK, SETUP, 3 ITEMs, WINNER, OUTRO) for N=3."
    
    # 1. Good Monologue
    good_xml = build_fake_monologue(plan_n3, "savage_roast_master")
    parsed = parse_monologue(good_xml, plan_n3)
    assert len(parsed) == len(plan_n3.segments)
    logger.info("PASS: Good monologue parsed successfully.")
    
    # 2. Missing Tag
    bad_missing = build_bad_monologue_missing_tag(plan_n3)
    try:
        parse_monologue(bad_missing, plan_n3)
        assert False, "Should have raised ScriptParsingError"
    except ScriptParsingError as e:
        assert "Missing" in str(e)
        logger.info("PASS: Missing tag caught correctly.")
        
    # 3. Unknown Tag
    bad_unknown = build_bad_monologue_unknown_tag(plan_n3)
    try:
        parse_monologue(bad_unknown, plan_n3)
        assert False, "Should have raised ScriptParsingError"
    except ScriptParsingError as e:
        assert "unknown" in str(e).lower() or "invalid top-level content" in str(e).lower()
        logger.info("PASS: Unknown tag caught correctly.")

def test_length_violations():
    logger.info("--- Testing Offline Length Violations ---")
    dataset = get_dummy_dataset(num_rows=3)
    plan = build_segment_plan("job_123", "bar_chart", "savage_roast_master", dataset)
    
    bad_short = build_bad_monologue_too_short(plan)
    parsed = parse_monologue(bad_short, plan)
    
    seg_map = {s.tag: s for s in parsed}
    failing = _get_failing_segments(seg_map, plan)
    
    assert len(failing) >= 1, "Should have identified at least one failing segment"
    assert "Too short" in failing[0][1]
    logger.info("PASS: Length violations caught accurately.")

def test_runner_idempotency():
    logger.info("--- Testing Offline Runner Idempotency ---")
    from src.agents.phase2_scripting.runner import run_scripting
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        job_dir = tmp_path / "job_123"
        job_dir.mkdir(parents=True)
        
        dataset = get_dummy_dataset(num_rows=3)
        dataset_path = job_dir / "bar_chart_dataset.json"
        dataset_path.write_text(json.dumps(dataset.model_dump()))
        
        jm = MagicMock(spec=JobManager)
        jm.job_id = "job_123"
        jm.job_dir = job_dir
        jm.get_logger.return_value = logger
        jm.get_step_metadata.return_value = {"template": "bar_chart"}
        
        with patch("src.agents.phase2_scripting.runner.write_script") as mock_ws:
            plan = build_segment_plan("job_123", "bar_chart", "savage_roast_master", dataset)
            good_xml = build_fake_monologue(plan, "savage_roast_master")
            parsed = parse_monologue(good_xml, plan)
            mock_ws.return_value = (parsed, "mock history")
            
            # Initial run
            payload1 = asyncio.run(run_scripting(jm, persona_id="savage_roast_master"))
            assert mock_ws.call_count == 1
            assert (job_dir / "script" / "script.json").exists()
            logger.info("PASS: First run generated and saved script properly.")
            
            # Subsequence Cached Run
            payload2 = asyncio.run(run_scripting(jm, persona_id="savage_roast_master"))
            assert mock_ws.call_count == 1  # Verify the mocked function was NOT arbitrarily called again
            assert payload1.inputs_hash == payload2.inputs_hash
            logger.info("PASS: Second run seamlessly hit cache returning identical outputs natively.")

if __name__ == "__main__":
    try:
        test_timing_and_parsing()
        test_length_violations()
        test_runner_idempotency()
        print("\n=== OFFLINE TESTS: ALL PASS ===")
    except Exception as e:
        print(f"\n=== OFFLINE TESTS: FAIL ===")
        print(e)
        raise
