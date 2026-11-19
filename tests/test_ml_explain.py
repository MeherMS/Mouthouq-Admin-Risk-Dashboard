import numpy as np
import pandas as pd

from app.ml.default_model import MODEL_FEATURES, fit_default_model
from app.ml.explain import check_additivity, contributions, top_factors
from app.ml.features import ALL_FEATURES


def synthetic_frame(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, len(ALL_FEATURES))), columns=ALL_FEATURES)
    df["trouble_share"] = rng.uniform(0, 1, n)
    logit = 3 * df["trouble_share"] - 1.5
    df["default_label"] = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


def test_additivity_is_exact():
    df = synthetic_frame()
    model = fit_default_model(df.iloc[:1500])
    assert check_additivity(model, df.iloc[1500:]) < 1e-8


def test_sign_matches_the_signal():
    df = synthetic_frame()
    model = fit_default_model(df.iloc[:1500])
    coef = model.named_steps["logisticregression"].coef_[0]
    test = df.iloc[1500:]
    c = contributions(model, test)
    assert coef[MODEL_FEATURES.index("trouble_share")] > 0
    assert c.loc[test["trouble_share"] > 0.9, "trouble_share"].mean() > 0
    assert c.loc[test["trouble_share"] < 0.1, "trouble_share"].mean() < 0


def test_top_factors_shape_order_and_direction():
    df = synthetic_frame()
    model = fit_default_model(df.iloc[:1500])
    tf = top_factors(model, df.iloc[1500:1510], k=3)
    for factors in tf:
        assert len(factors) == 3
        mags = [abs(f["contribution"]) for f in factors]
        assert mags == sorted(mags, reverse=True)
        for f in factors:
            expected = "raises risk" if f["contribution"] > 0 else "lowers risk"
            assert f["direction"] == expected