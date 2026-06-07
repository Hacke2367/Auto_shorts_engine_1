"""Offline coverage for the Phase 2 script-doctor flow pass.

Mocks `_call_gemini` so `write_script` runs end-to-end (including the doctor) with no API key.
Covers three branches: doctor applies a valid polish, doctor falls back on a bad polish, and the
doctor is skipped when disabled.
"""

import asyncio
import logging

from unittest.mock import patch

from tests.phase2_scripting.dummy_phase1_outputs import get_dummy_dataset
from tests.phase2_scripting.fake_llm import build_fake_monologue
from src.agents.phase2_scripting.timing import build_segment_plan
from src.agents.phase2_scripting import llm_writer

logger = logging.getLogger(__name__)


def _make_plan_and_dataset(rows=3, template="bar_chart", persona="savage_roast_master"):
    dataset = get_dummy_dataset(num_rows=rows, template=template)
    plan = build_segment_plan("job_doc_test", template, persona, dataset)
    return plan, dataset


def _run(plan, dataset, fake_call, doctor_enabled):
    orig = llm_writer.APP_CONFIG.script_doctor_enabled
    llm_writer.APP_CONFIG.script_doctor_enabled = doctor_enabled
    try:
        with patch.object(llm_writer, "_call_gemini", fake_call):
            return asyncio.run(llm_writer.write_script(plan, dataset, session=None, log=logger))
    finally:
        llm_writer.APP_CONFIG.script_doctor_enabled = orig


def test_doctor_applies_when_polish_is_valid():
    plan, dataset = _make_plan_and_dataset()

    async def fake_call(system_prompt, user_prompt, session, log, phase_model=None, cost_phase=""):
        # Both main generation and the doctor get a valid, in-budget monologue.
        return build_fake_monologue(plan, plan.persona_id)

    segs, history = _run(plan, dataset, fake_call, doctor_enabled=True)

    assert len(segs) == len(plan.segments)
    for s in segs:
        assert s.target_min_chars <= s.char_count <= s.target_max_chars
    assert "[APPLIED]" in history


def test_doctor_falls_back_on_bad_polish():
    plan, dataset = _make_plan_and_dataset()

    async def fake_call(system_prompt, user_prompt, session, log, phase_model=None, cost_phase=""):
        # Doctor pass returns a structurally broken monologue -> must be discarded.
        if "PERFORMANCE DOCTOR" in user_prompt:
            return "<MONOLOGUE><HOOK>broken</HOOK></MONOLOGUE>"
        return build_fake_monologue(plan, plan.persona_id)

    segs, history = _run(plan, dataset, fake_call, doctor_enabled=True)

    # Fell back to the valid pre-doctor script — never worsened, never crashed.
    assert len(segs) == len(plan.segments)
    for s in segs:
        assert s.target_min_chars <= s.char_count <= s.target_max_chars
    assert "DISCARDED" in history


def test_doctor_skipped_when_disabled():
    plan, dataset = _make_plan_and_dataset()

    async def fake_call(system_prompt, user_prompt, session, log, phase_model=None, cost_phase=""):
        assert "PERFORMANCE DOCTOR" not in user_prompt, "doctor must not run when disabled"
        return build_fake_monologue(plan, plan.persona_id)

    segs, history = _run(plan, dataset, fake_call, doctor_enabled=False)

    assert len(segs) == len(plan.segments)
    assert "Script Doctor" not in history


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_doctor_applies_when_polish_is_valid()
    test_doctor_falls_back_on_bad_polish()
    test_doctor_skipped_when_disabled()
    print("=== SCRIPT DOCTOR TESTS: ALL PASS ===")
