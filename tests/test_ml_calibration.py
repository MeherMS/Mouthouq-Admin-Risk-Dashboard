import numpy as np

from app.ml.calibration import apply_platt, fit_platt


def test_recovers_a_known_logit_shift():
    rng = np.random.default_rng(0)
    p_true = rng.uniform(0.01, 0.5, 50_000)
    y = rng.uniform(size=p_true.size) < p_true
    # Systematically overpredict: shift every logit up by 1.
    logit_bad = np.log(p_true / (1 - p_true)) + 1.0
    p_bad = 1 / (1 + np.exp(-logit_bad))
    platt = fit_platt(y, p_bad)
    assert abs(platt.intercept_[0] - (-1.0)) < 0.1
    assert abs(platt.coef_[0][0] - 1.0) < 0.1


def test_identity_on_calibrated_input():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.01, 0.5, 50_000)
    y = rng.uniform(size=p.size) < p
    platt = fit_platt(y, p)
    out = apply_platt(platt, p)
    assert np.abs(out - p).mean() < 0.01


def test_outputs_are_probabilities():
    rng = np.random.default_rng(2)
    p = rng.uniform(0, 1, 1000)
    y = rng.uniform(size=p.size) < p
    out = apply_platt(fit_platt(y, p), p)
    assert out.min() >= 0.0 and out.max() <= 1.0