from pathlib import Path


def test_response_pattern_docs_include_required_templates() -> None:
    content = Path("skills/resilience/response-patterns.md").read_text(encoding="utf-8")

    assert "Calm Recovery" in content
    assert "Uncertainty Disclosure" in content
    assert "Tool Failure" in content
    assert "Anti-Fabrication" in content
    assert "Tradeoff Reframing" in content
    assert "Partial Analysis Recovery" in content
    assert "Dishonest Reporting Refusal" in content
