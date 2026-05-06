from runtime.integrity_guard import run_integrity_checkpoint


def test_completion_claim_requires_verification() -> None:
    checkpoint = run_integrity_checkpoint("It is fixed and done.", signals=("completion_claim",))

    assert checkpoint.completion_claim_requires_verification
    assert "Do not claim completion" in checkpoint.recommended_disclosure


def test_verified_completion_does_not_require_extra_verification() -> None:
    checkpoint = run_integrity_checkpoint("The fix is done and the test passed.")

    assert not checkpoint.completion_claim_requires_verification
