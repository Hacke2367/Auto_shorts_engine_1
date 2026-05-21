import json
from src.agents.phase1_discovery.candidate_score import _parse_scoring_response

def main():
    fake_topic = "Nvidia vs AMD data center revenue race"
    fake_snippet = "Nvidia reached $20B in data center revenue while AMD hit $4B in Q4 2024."

    fake_llm_response = json.dumps({
        "rationale": "Strong rivalry, clear data, high visual potential.",
        "validation_confidence": "high",  # Changed from integer 8 to string as per your prompt rules
        "hook_potential_score": 9,
        "novelty_score": 7,
        "visual_fit_score": 9,
        "data_feasibility_score": 8,
        "freshness_score": 8,
        "best_fit_template": "vs_card",
        "fit_reason": "Two-entity rivalry with strong head-to-head framing.",
        "source_hint": "quarterly revenue reports"
    })

    # FIXED: Added the missing 3rd argument (fake_snippet)
    result = _parse_scoring_response(fake_llm_response, fake_topic, fake_snippet)

    print("PARSED RESULT:")
    print(result)

    assert result is not None, "Parser returned None"
    assert result.best_fit_template == "vs_card"
    assert result.hook_potential_score == 9.0
    assert result.novelty_score == 7.0
    assert result.visual_fit_score == 9.0
    assert result.data_feasibility_score == 8.0
    assert result.freshness_score == 8.0

    print("\n✅ PASS: candidate_score parser working correctly")

if __name__ == "__main__":
    main()