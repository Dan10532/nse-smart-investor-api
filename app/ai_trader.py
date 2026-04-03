def trading_decision(pe, roe, debt_ratio):
    """
    Simple rule-based trading signal.
    BUY  — low PE, strong ROE, low debt
    SELL — overvalued PE or dangerously high debt
    HOLD — everything else
    """
    if pe is None:
        return "HOLD"

    if pe < 10 and roe is not None and roe > 0.15 and debt_ratio is not None and debt_ratio < 0.5:
        return "BUY"

    if pe > 20 or (debt_ratio is not None and debt_ratio > 0.7):
        return "SELL"

    return "HOLD"
