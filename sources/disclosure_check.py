def compare_structured_and_disclosed_periods(
    latest_structured_period: str | None,
    latest_disclosure_period: str | None,
) -> str:
    if not latest_disclosure_period:
        return "unknown"
    if not latest_structured_period:
        return "pending_structured_data"
    if latest_structured_period == latest_disclosure_period:
        return "current"
    return "stale"

