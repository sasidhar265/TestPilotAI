from app.generator import copilot_error_message


def test_authentication_error_has_actionable_message() -> None:
    assert "copilot login" in copilot_error_message(Exception("401 not authenticated"))


def test_policy_error_has_actionable_message() -> None:
    assert "Copilot CLI policy" in copilot_error_message(Exception("403 forbidden by policy"))


def test_premium_limit_has_actionable_message() -> None:
    assert "premium requests" in copilot_error_message(Exception("429 rate limit"))
