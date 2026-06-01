"""The F1Predict simulation engine.

Pipeline (see docs/science/):
    deterministic physics  ->  ML residual  ->  skewed-t noise  ->  Monte Carlo
    strategy evaluation / optimization sits on top of the lap-time model.
"""
