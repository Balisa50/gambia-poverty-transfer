"""
Conformal prediction, and the assumption it rests on.

Why this is the measurement instrument
--------------------------------------
Split conformal prediction comes with a finite-sample guarantee: an interval
built at level 1 - alpha contains the truth with probability at least 1 - alpha,
for any underlying model, with no distributional assumptions about the data.

The guarantee has one requirement. Calibration and test data must be
**exchangeable**. Cross-border transfer is precisely the situation where that
fails: Gambian clusters are not exchangeable with Senegalese or Malian ones.

That is why conformal is the centrepiece here rather than quantile regression or
a bootstrap. Watching a method with a proof attached lose its coverage is a
cleaner demonstration than watching a heuristic degrade, because with a
heuristic nobody expected a guarantee in the first place. If coverage holds
in-country and drops out-of-country, the drop is attributable to the broken
assumption rather than to a model being poorly tuned.

``_selftest`` demonstrates both halves on synthetic data: coverage holds under
exchangeability, and breaks under covariate shift.

The calibration set must come from training countries
-----------------------------------------------------
Calibrating on Gambian clusters would restore coverage by construction and
destroy the experiment. ``SplitConformal.calibrate`` refuses data carrying the
target country label; see docs/03-training-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Fraction of truths falling inside the interval."""
    y, lo, hi = map(np.asarray, (y, lo, hi))
    return float(np.mean((y >= lo) & (y <= hi)))


def mean_width(lo: np.ndarray, hi: np.ndarray) -> float:
    """Average interval width. Must always be read next to coverage.

    An interval that covers 90% by being uselessly wide is not calibrated in any
    useful sense, and reporting coverage alone would hide that.
    """
    return float(np.mean(np.asarray(hi) - np.asarray(lo)))


def interval_score(y: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                   alpha: float) -> float:
    """Winkler interval score: width plus a penalty for each miss. Lower better.

    Combines coverage and sharpness in one number, so a model cannot win by
    inflating its intervals.
    """
    y, lo, hi = map(np.asarray, (y, lo, hi))
    width = hi - lo
    below = (2.0 / alpha) * np.clip(lo - y, 0, None)
    above = (2.0 / alpha) * np.clip(y - hi, 0, None)
    return float(np.mean(width + below + above))


def calibration_curve(y: np.ndarray, predict_interval, levels=None) -> list[dict]:
    """Empirical coverage across a range of nominal levels, not just one.

    A method can be right at 90% and wrong everywhere else, so the whole curve
    is reported rather than a single point.
    """
    levels = levels if levels is not None else [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    rows = []
    for lv in levels:
        lo, hi = predict_interval(1.0 - lv)
        rows.append({"nominal": lv,
                     "empirical": coverage(y, lo, hi),
                     "width": mean_width(lo, hi)})
    return rows


# --------------------------------------------------------------------------- #
# Split conformal
# --------------------------------------------------------------------------- #
@dataclass
class SplitConformal:
    """Split conformal prediction with absolute-residual scores.

    Produces constant-width intervals. Simple, and the width is exactly what the
    calibration distribution says it should be, which makes any coverage failure
    easy to attribute.
    """

    model: object
    scores_: np.ndarray | None = field(default=None, init=False)

    def fit(self, X, y) -> "SplitConformal":
        self.model.fit(X, y)
        return self

    def calibrate(self, X, y, countries=None, exclude: str | None = None
                  ) -> "SplitConformal":
        """Compute nonconformity scores on held-out calibration data.

        ``exclude`` guards the experiment. Calibrating on target-country
        clusters would restore coverage by construction, so it is refused here
        rather than left to discipline.
        """
        if exclude is not None:
            if countries is None:
                raise ValueError("exclude given without country labels")
            countries = np.asarray(countries)
            if (countries == exclude).any():
                raise ValueError(
                    f"calibration set contains {exclude}, the target country. "
                    "Calibrating on the target restores coverage by "
                    "construction and invalidates the experiment.")
        self.scores_ = np.abs(np.asarray(y) - self.model.predict(X))
        return self

    def predict_interval(self, X, alpha: float = 0.1):
        """Return (lo, hi) at level 1 - alpha.

        Uses the ceil((n+1)(1-alpha))/n empirical quantile of calibration
        scores, the finite-sample correction that makes the guarantee exact
        rather than asymptotic.
        """
        if self.scores_ is None:
            raise RuntimeError("call calibrate() before predict_interval()")
        n = len(self.scores_)
        k = int(np.ceil((n + 1) * (1 - alpha)))
        if k > n:
            raise ValueError(
                f"calibration set of {n} is too small for alpha={alpha}; "
                f"need at least {int(np.ceil(1 / alpha)) - 1}")
        q = np.sort(self.scores_)[k - 1]
        pred = self.model.predict(X)
        return pred - q, pred + q


@dataclass
class ConformalizedQuantile:
    """Conformalized quantile regression (CQR).

    Fits quantile models at alpha/2 and 1 - alpha/2, then conformalises their
    output. Unlike absolute-residual conformal, the interval width varies with
    the input, so it can be narrow where the model is confident and wide where
    it is not.

    Included because adaptivity is the property most likely to survive a
    distribution shift. If constant-width conformal loses coverage but CQR does
    not, that is informative; if both lose it, the failure is about the shift
    rather than about interval shape.
    """

    model_lo: object
    model_hi: object
    alpha: float = 0.1
    scores_: np.ndarray | None = field(default=None, init=False)

    def fit(self, X, y) -> "ConformalizedQuantile":
        self.model_lo.fit(X, y)
        self.model_hi.fit(X, y)
        return self

    def calibrate(self, X, y, countries=None, exclude: str | None = None
                  ) -> "ConformalizedQuantile":
        if exclude is not None:
            if countries is None:
                raise ValueError("exclude given without country labels")
            if (np.asarray(countries) == exclude).any():
                raise ValueError(
                    f"calibration set contains {exclude}, the target country.")
        y = np.asarray(y)
        lo, hi = self.model_lo.predict(X), self.model_hi.predict(X)
        # Score is how far outside the predicted band the truth falls; negative
        # when it is comfortably inside, which is what lets CQR shrink intervals.
        self.scores_ = np.maximum(lo - y, y - hi)
        return self

    def predict_interval(self, X, alpha: float | None = None):
        if self.scores_ is None:
            raise RuntimeError("call calibrate() before predict_interval()")
        alpha = self.alpha if alpha is None else alpha
        n = len(self.scores_)
        k = int(np.ceil((n + 1) * (1 - alpha)))
        if k > n:
            raise ValueError(f"calibration set of {n} too small for alpha={alpha}")
        q = np.sort(self.scores_)[k - 1]
        return self.model_lo.predict(X) - q, self.model_hi.predict(X) + q


# --------------------------------------------------------------------------- #
def _selftest() -> None:
    """Coverage holds under exchangeability, and breaks under covariate shift.

    This is the mechanism the whole project rests on, shown on synthetic data
    before any real data exists. If conformal did not lose coverage under shift,
    there would be nothing to measure in The Gambia.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    print("=== conformal.py self-test ===\n")
    rng = np.random.default_rng(11)
    d, n = 5, 6000

    def make(n_, shift=0.0):
        X = rng.normal(shift, 1.0, size=(n_, d))
        # Heteroscedastic on purpose: noise grows with the first feature, so a
        # shift in X also shifts the noise scale. This is what a real domain
        # shift looks like, and what constant-width intervals cannot track.
        noise = rng.normal(0, 0.3 + 0.6 * np.abs(X[:, 0]), size=n_)
        y = 2 * X[:, 0] - 1.5 * X[:, 1] + 0.8 * X[:, 2] ** 2 + noise
        return X, y

    X, y = make(n)
    Xtr, ytr = X[:3000], y[:3000]
    Xcal, ycal = X[3000:4500], y[3000:4500]
    Xte, yte = X[4500:], y[4500:]
    Xsh, ysh = make(1500, shift=1.5)          # covariate shift, "another country"

    ALPHA = 0.10
    print(f"  nominal coverage: {1 - ALPHA:.0%}\n")
    print(f"{'method':<26}{'setting':<16}{'coverage':>10}{'width':>9}{'score':>9}")

    # --- absolute-residual conformal ---
    sc = SplitConformal(GradientBoostingRegressor(random_state=0)).fit(Xtr, ytr)
    sc.calibrate(Xcal, ycal)
    for label, (Xe, ye) in [("exchangeable", (Xte, yte)), ("shifted", (Xsh, ysh))]:
        lo, hi = sc.predict_interval(Xe, ALPHA)
        print(f"{'split conformal':<26}{label:<16}{coverage(ye, lo, hi):>10.3f}"
              f"{mean_width(lo, hi):>9.2f}{interval_score(ye, lo, hi, ALPHA):>9.2f}")

    # --- CQR ---
    q = lambda a: GradientBoostingRegressor(loss="quantile", alpha=a, random_state=0)
    cq = ConformalizedQuantile(q(ALPHA / 2), q(1 - ALPHA / 2), alpha=ALPHA).fit(Xtr, ytr)
    cq.calibrate(Xcal, ycal)
    cov = {}
    for label, (Xe, ye) in [("exchangeable", (Xte, yte)), ("shifted", (Xsh, ysh))]:
        lo, hi = cq.predict_interval(Xe, ALPHA)
        cov[label] = coverage(ye, lo, hi)
        print(f"{'CQR':<26}{label:<16}{cov[label]:>10.3f}"
              f"{mean_width(lo, hi):>9.2f}{interval_score(ye, lo, hi, ALPHA):>9.2f}")

    # --- the two claims this file has to support ---
    lo, hi = sc.predict_interval(Xte, ALPHA)
    cov_ok = coverage(yte, lo, hi)
    lo, hi = sc.predict_interval(Xsh, ALPHA)
    cov_shift = coverage(ysh, lo, hi)

    assert cov_ok >= 1 - ALPHA - 0.02, (
        f"coverage should hold under exchangeability, got {cov_ok:.3f}")
    assert cov_shift < 1 - ALPHA - 0.02, (
        f"coverage should degrade under shift, got {cov_shift:.3f}")

    print(f"\n  Under exchangeability, coverage {cov_ok:.3f} meets the "
          f"{1 - ALPHA:.0%} guarantee.")
    print(f"  Under covariate shift, coverage falls to {cov_shift:.3f}, a "
          f"shortfall of {(1 - ALPHA) - cov_shift:.3f}.")
    print("  The guarantee assumes exchangeability. Crossing a border breaks it.")
    print("  That shortfall is what this project measures for The Gambia.")

    # --- the guard on the calibration set ---
    print("\n--- calibration-set guard ---")
    countries = np.array(["SN"] * 1000 + ["GM"] * 500)
    try:
        SplitConformal(GradientBoostingRegressor(random_state=0)).fit(
            Xtr, ytr).calibrate(Xcal, ycal, countries=countries, exclude="GM")
        raise AssertionError("guard failed to fire")
    except ValueError as e:
        print(f"  refused, as intended: {str(e)[:72]}...")


if __name__ == "__main__":
    _selftest()
