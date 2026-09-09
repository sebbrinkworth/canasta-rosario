import numpy as np
import pandas as pd

from forecast.backtest import contiguous_history, drift_pred
from forecast.evaluate_history import build_examples, paired_change, trailing_history


def test_missing_calendar_days_reset_model_context():
    h = np.array([100., 100., 101., 101., np.nan, np.nan, 200., 201.])
    assert trailing_history(h, len(h)).tolist() == [200., 201.]
    series = pd.Series(h)
    assert contiguous_history(series).tolist() == [200., 201.]
    assert drift_pred(series) is None


def test_only_observed_adjacent_targets_and_no_future_feature_leakage():
    index = pd.date_range("2026-07-01", periods=12)
    panel = pd.DataFrame({"rice__12": [100., 100., 100., 100., 105., np.nan, np.nan, np.nan, 110., 110., 110., 110.]}, index=index)
    desc = pd.DataFrame("same", index=index, columns=panel.columns)
    examples, x, _, _ = build_examples(panel, desc)
    assert [r["date"] for r in examples] == ["2026-07-05"]
    modified = panel.copy()
    modified.iloc[4:, 0] = 999
    later, x2, _, _ = build_examples(modified, desc)
    first = next(i for i, r in enumerate(later) if r["date"] == "2026-07-05")
    assert np.array_equal(x[0], x2[first])


def test_paired_evaluation_rejects_changed_targets():
    import pytest
    row = {"date": "2026-09-01", "series": "rice__12", "actual": 110., "last": 100., "predictions": {"persistence": 100.}}
    assert paired_change([row], [row], "persistence")["mae_delta"] == 0
    with pytest.raises(ValueError, match="changed target"):
        paired_change([row], [{**row, "actual": 120.}], "persistence")
