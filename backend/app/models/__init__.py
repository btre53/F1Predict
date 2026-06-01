"""Model bake-off: candidate F1 prediction models on a shared, forward-chained,
calibration-first evaluation harness (see docs/science/09-modeling-bakeoff.md).

Pipeline shared by every candidate:
    per-race features -> model produces driver "strengths" -> Plackett-Luce/discounted
    -Harville -> win/podium/points probabilities -> (optional) Benter market-blend
    -> forward-chained scoring vs actual results and vs the Polymarket market.
"""
