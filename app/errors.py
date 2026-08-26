def copilot_error_message(error: Exception) -> str:
    """Return actionable Copilot failures without leaking provider responses."""
    message = str(error).casefold()
    if "auth" in message or "401" in message or "credential" in message:
        return (
            "GitHub Copilot is not authenticated. Run 'copilot login' or configure "
            "COPILOT_GITHUB_TOKEN, then restart."
        )
    if "403" in message or "forbidden" in message or "policy" in message:
        return (
            "GitHub Copilot access was denied. Ask your organization administrator to enable "
            "the Copilot CLI policy for your account."
        )
    if "rate" in message or "429" in message or "premium request" in message:
        return "GitHub Copilot usage is temporarily limited or its premium requests are exhausted."
    return "GitHub Copilot generation failed. Check the server logs and Copilot CLI status."
