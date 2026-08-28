"""
Simulation checks on the two instruments, on data where the truth is known.

Both experiments in this paper rest on a measurement whose correctness cannot be
checked against the real data, because with real data there is no ground truth to
compare against. On synthetic data there is.

  Panel A  Spatial blocking. Points carry an unobserved short-range field that
           the covariates do not contain. A random split lets a flexible model
           find a test point's near neighbours in training and recover their
           local conditions; a blocked split removes those neighbours. The gap
           between the two scores is leakage, and it is present by construction,
           so a blocking scheme that does not reveal it is not working.

  Panel B  Conformal coverage. Calibration and test data are drawn first from the
           same distribution, then from shifted ones. Coverage should hold in the
           first case, because that is what the guarantee promises, and is free
           to fail in the second, because exchangeability is what the guarantee
           requires.

Neither panel uses DHS data. Both are deterministic given the seeds below.

Run:  python src/make_sim_figure.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold

from conformal import SplitConformal, coverage
from splits import assign_blocks, blocked_kfold

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"

plt.rcParams.update({
    "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.bbox": "tight",
})

LEVELS = [0.50, 0.80, 0.90, 0.95]


def spatial_leakage(seed: int = 7, side: int = 40):
    """R-squared under a random split and under a spatially blocked split."""
    rng = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.linspace(0, 6, side), np.linspace(0, 6, side))
    lon = gx.ravel() + rng.normal(0, 0.02, side * side)
    lat = gy.ravel() + rng.normal(0, 0.02, side * side)

    def field(freq, s):
        r = np.random.default_rng(s)
        out = np.zeros_like(lon)
        for _ in range(6):
            a, b = r.normal(0, freq, 2)
            out += np.sin(a * lon + b * lat + r.uniform(0, 2 * np.pi))
        return out / 6

    # Observed covariates vary slowly, so they encode roughly where a point is.
    X = np.column_stack([field(0.8, s) for s in (1, 2, 3)])
    # Local conditions vary quickly and are absent from X, standing in for
    # whatever a real covariate set fails to measure.
    local = field(4.0, 99)
    y = 2 * X[:, 0] - X[:, 1] + 1.5 * local + rng.normal(0, 0.05, len(lon))

    def model():
        return RandomForestRegressor(n_estimators=120, random_state=0, n_jobs=-1)

    rand = [r2_score(y[te], model().fit(X[tr], y[tr]).predict(X[te]))
            for tr, te in KFold(5, shuffle=True, random_state=0).split(X)]

    folds = blocked_kfold(assign_blocks(lon, lat, block_km=80.0), n_folds=5)
    blocked = [r2_score(y[folds == f],
                        model().fit(X[folds != f], y[folds != f]).predict(X[folds == f]))
               for f in range(5)]
    return float(np.mean(rand)), float(np.mean(blocked))


def conformal_shift(seed: int = 3, n: int = 4000):
    """Coverage at each nominal level, under exchangeability and under shift."""
    rng = np.random.default_rng(seed)
    d = 4

    def draw(n_, centre):
        X = rng.normal(centre, 1.0, (n_, d))
        # Heteroscedastic noise, so a constant-width interval is not automatically
        # right and the calibration set has to do real work.
        y = X[:, 0] * 2 + np.sin(X[:, 1] * 2) + rng.normal(0, 0.4 + 0.3 * np.abs(X[:, 2]))
        return X, y

    Xtr, ytr = draw(n, 0.0)
    Xcal, ycal = draw(n // 2, 0.0)
    Xsame, ysame = draw(n // 2, 0.0)      # exchangeable with calibration
    Xshift, yshift = draw(n // 2, 1.0)    # covariate shift

    cp = SplitConformal(GradientBoostingRegressor(random_state=0)).fit(Xtr, ytr)
    cp.calibrate(Xcal, ycal)

    same, shifted = [], []
    for lvl in LEVELS:
        a = 1 - lvl
        lo, hi = cp.predict_interval(Xsame, alpha=a)
        same.append(coverage(ysame, lo, hi))
        lo, hi = cp.predict_interval(Xshift, alpha=a)
        shifted.append(coverage(yshift, lo, hi))
    return same, shifted


def main() -> None:
    FIG.mkdir(exist_ok=True)
    print("running simulations")
    r_rand, r_block = spatial_leakage()
    same, shifted = conformal_shift()
    print(f"  A  random {r_rand:.3f}  blocked {r_block:.3f}  "
          f"leakage {r_rand - r_block:.3f}")
    print(f"  B  exchangeable {same[2]:.3f}  shifted {shifted[2]:.3f} "
          f"(nominal 0.90)")

    fig, (a, b) = plt.subplots(1, 2, figsize=(7.6, 2.9))
    fig.subplots_adjust(wspace=0.38)

    a.bar([0, 1], [r_rand, r_block], width=0.55,
          color=["#b0b0b0", "#1a1a1a"])
    a.set_xticks([0, 1])
    a.set_xticklabels(["random split", "spatially\nblocked"])
    a.set_ylabel("$R^2$ on held-out points")
    a.set_ylim(0, 1.0)
    a.set_title("A. Blocking exposes spatial leakage", fontsize=9, loc="left")
    # Arrow to the right of both bars. Drawn over the second bar it landed on
    # that bar's own value label.
    ax_x = 1.45
    a.annotate("", xy=(ax_x, r_block), xytext=(ax_x, r_rand),
               arrowprops=dict(arrowstyle="<->", lw=0.9, color="#c1272d"))
    a.hlines([r_rand, r_block], [0, 1], ax_x, color="#c1272d", lw=0.5,
             ls=":", zorder=0)
    a.text(ax_x + 0.1, (r_rand + r_block) / 2,
           f"leakage\n{r_rand - r_block:.3f}",
           fontsize=8, color="#c1272d", va="center", ha="left")
    a.set_xlim(-0.55, 2.3)
    for x, v in zip([0, 1], [r_rand, r_block]):
        a.text(x, v + 0.025, f"{v:.3f}", ha="center", fontsize=8)

    b.plot([0.45, 1.0], [0.45, 1.0], color="#c1272d", lw=1, zorder=1)
    b.plot(LEVELS, same, "o-", ms=4, color="#1a1a1a", label="exchangeable")
    b.plot(LEVELS, shifted, "s-", ms=4, color="#1a5490", label="covariate shift")
    b.set_xlabel("nominal coverage")
    b.set_ylabel("empirical coverage")
    b.set_xlim(0.45, 1.0)
    b.set_ylim(0.30, 1.0)
    b.legend(loc="upper left", frameon=False, fontsize=8)
    b.set_title("B. Coverage holds, then fails under shift", fontsize=9,
                loc="left")

    fig.savefig(FIG / "fig3_simulation.pdf")
    plt.close(fig)
    print("  fig3_simulation.pdf")


if __name__ == "__main__":
    main()
