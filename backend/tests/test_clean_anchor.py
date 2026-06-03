"""Clean-air pace anchor for the sim (task #24 step 1)."""

import numpy as np

from app.models.clean_anchor import forward_clean_anchor


def test_anchor_is_forward_chained_and_sane():
    a = forward_clean_anchor()
    assert len(a) > 100                       # most races get a clean-pace strength
    last = max(a)
    vals = np.array(list(a[last].values()))
    assert len(vals) >= 4
    assert np.all(np.isfinite(vals))
    # z-scored combination -> roughly centred, real spread (it identifies fast vs slow cars)
    assert abs(float(vals.mean())) < 0.5 and float(vals.std()) > 0.2
