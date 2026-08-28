"""
Spatially blocked and leave-one-country-out splits.

Why this file exists
--------------------
DHS clusters are spatially autocorrelated. Two clusters 8 km apart share
nightlights, land cover, roads and market access, so a random train/test split
puts near-neighbours on both sides of it. The model is then partly tested on
places it has effectively already seen, and the reported accuracy is too high.

For this project that is not a minor inefficiency. The entire claim is a
comparison between in-country and out-of-country performance. If the in-country
number is inflated by leakage, the drop at the border looks larger than it
really is, and the paper measures our own carelessness rather than a property of
the models.

``_selftest`` below demonstrates the effect on synthetic data instead of
asserting it: the same model, the same data, scored under a random split and
under a spatially blocked split.

See docs/03-training-design.md for how these splits are used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd

WGS84 = "EPSG:4326"


# --------------------------------------------------------------------------- #
# Spatial blocking
# --------------------------------------------------------------------------- #
def assign_blocks(lon: np.ndarray, lat: np.ndarray,
                  block_km: float = 50.0) -> np.ndarray:
    """Assign each point to a square spatial block, returning integer block ids.

    Blocks are laid out on a metric grid, not a degree grid, because a degree of
    longitude shrinks with latitude and degree-square blocks would vary in size
    across the study area.

    ``block_km`` must comfortably exceed the covariate correlation range. It is
    estimated empirically from a residual variogram rather than assumed; see
    ``correlation_range`` below.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)

    # Local metric approximation, accurate enough for gridding at this scale.
    km_per_deg_lat = 110.574
    km_per_deg_lon = 111.320 * np.cos(np.radians(lat.mean()))

    x_km = (lon - lon.min()) * km_per_deg_lon
    y_km = (lat - lat.min()) * km_per_deg_lat

    ix = np.floor(x_km / block_km).astype(int)
    iy = np.floor(y_km / block_km).astype(int)
    # Pair the two indices into one id.
    return ix * (iy.max() + 1) + iy


def blocked_kfold(block_ids: np.ndarray, n_folds: int = 5,
                  seed: int = 42) -> np.ndarray:
    """Assign whole blocks to folds, returning a fold index per point.

    Blocks are shuffled and dealt round-robin by descending size, which keeps
    fold sizes closer to equal than random assignment does when block sizes are
    very uneven, as they are for real survey data.
    """
    rng = np.random.default_rng(seed)
    blocks, counts = np.unique(block_ids, return_counts=True)

    order = np.argsort(-counts)
    blocks, counts = blocks[order], counts[order]
    # Break ties randomly so the result is not an artefact of block id order.
    jitter = rng.permutation(len(blocks))
    order = np.lexsort((jitter, -counts))
    blocks, counts = blocks[order], counts[order]

    fold_load = np.zeros(n_folds)
    block_to_fold: dict[int, int] = {}
    for b, c in zip(blocks, counts):
        f = int(np.argmin(fold_load))
        block_to_fold[int(b)] = f
        fold_load[f] += c

    return np.array([block_to_fold[int(b)] for b in block_ids])


def correlation_range(lon: np.ndarray, lat: np.ndarray, values: np.ndarray,
                      max_km: float = 200.0, n_bins: int = 20) -> pd.DataFrame:
    """Empirical semivariogram, used to choose a defensible block size.

    Returns mean squared difference between pairs of points against the distance
    separating them. The distance at which it flattens is the range beyond which
    points are effectively independent, and the block size should exceed it.

    Computed on a random subsample of pairs, since the full pair count is
    quadratic in the number of clusters.
    """
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    values = np.asarray(values, float)
    n = len(lon)

    rng = np.random.default_rng(0)
    n_pairs = min(200_000, n * (n - 1) // 2)
    i = rng.integers(0, n, n_pairs)
    j = rng.integers(0, n, n_pairs)
    keep = i != j
    i, j = i[keep], j[keep]

    km_per_deg_lat = 110.574
    km_per_deg_lon = 111.320 * np.cos(np.radians(lat.mean()))
    dx = (lon[i] - lon[j]) * km_per_deg_lon
    dy = (lat[i] - lat[j]) * km_per_deg_lat
    dist = np.hypot(dx, dy)
    semivar = 0.5 * (values[i] - values[j]) ** 2

    bins = np.linspace(0, max_km, n_bins + 1)
    idx = np.digitize(dist, bins) - 1
    ok = (idx >= 0) & (idx < n_bins)

    rows = []
    for b in range(n_bins):
        sel = ok & (idx == b)
        if sel.sum() >= 30:
            rows.append({"dist_km": 0.5 * (bins[b] + bins[b + 1]),
                         "semivariance": semivar[sel].mean(),
                         "n_pairs": int(sel.sum())})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Leave-one-country-out
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Split:
    name: str
    train: np.ndarray   # boolean mask
    test: np.ndarray    # boolean mask

    def sizes(self) -> tuple[int, int]:
        return int(self.train.sum()), int(self.test.sum())


def leave_one_country_out(countries: np.ndarray,
                          exclude: str | None = None) -> Iterator[Split]:
    """Yield one split per country, holding that country out entirely.

    ``exclude`` names the target country, which must appear in neither side of
    any split. The Gambia is excluded from every stage of model development and
    is evaluated exactly once, at the end. See docs/03-training-design.md.
    """
    countries = np.asarray(countries)
    pool = countries if exclude is None else countries[countries != exclude]

    for c in sorted(set(pool.tolist())):
        test = countries == c
        train = (countries != c)
        if exclude is not None:
            train &= (countries != exclude)
        yield Split(name=c, train=train, test=test)


# --------------------------------------------------------------------------- #
def _selftest() -> None:
    """Show, on synthetic data, that random splits overstate accuracy.

    Points are laid on a jittered grid. Covariates are smooth spatial fields, so
    a point's covariate vector effectively encodes where it is. The target adds
    a short-range field that is NOT among the covariates, which stands in for
    local conditions a real model cannot observe.

    Under a random split, a flexible model can locate a test point from its
    covariates, find its near-neighbours in the training set, and recover their
    unobserved local conditions. Under a blocked split those neighbours are
    absent and it cannot. The difference between the two scores is the leakage.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold
    from sklearn.metrics import r2_score

    print("=== splits.py self-test (synthetic spatial data) ===\n")

    rng = np.random.default_rng(7)
    side = 40
    gx, gy = np.meshgrid(np.linspace(0, 6, side), np.linspace(0, 6, side))
    lon = gx.ravel() + rng.normal(0, 0.02, side * side)
    lat = gy.ravel() + rng.normal(0, 0.02, side * side)

    def smooth_field(freq: float, seed: int) -> np.ndarray:
        r = np.random.default_rng(seed)
        out = np.zeros_like(lon)
        for _ in range(6):
            a, b = r.normal(0, freq, 2)
            phase = r.uniform(0, 2 * np.pi)
            out += np.sin(a * lon + b * lat + phase)
        return out / 6

    # Observed covariates: long-wavelength, so they encode position.
    X = np.column_stack([smooth_field(0.8, s) for s in (1, 2, 3)])
    # Unobserved local conditions: short-wavelength, absent from X.
    local = smooth_field(4.0, 99)
    y = 2 * X[:, 0] - X[:, 1] + 1.5 * local + rng.normal(0, 0.05, len(lon))

    model = lambda: RandomForestRegressor(n_estimators=120, random_state=0, n_jobs=-1)

    # Random split.
    random_scores = []
    for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
        m = model().fit(X[tr], y[tr])
        random_scores.append(r2_score(y[te], m.predict(X[te])))

    # Spatially blocked split.
    blocks = assign_blocks(lon, lat, block_km=80.0)
    folds = blocked_kfold(blocks, n_folds=5)
    blocked_scores = []
    for f in range(5):
        te, tr = folds == f, folds != f
        m = model().fit(X[tr], y[tr])
        blocked_scores.append(r2_score(y[te], m.predict(X[te])))

    r_mean, b_mean = float(np.mean(random_scores)), float(np.mean(blocked_scores))
    print(f"  n points          : {len(lon)}")
    print(f"  n spatial blocks  : {len(set(blocks.tolist()))}")
    print(f"  random-split   R2 : {r_mean:.3f}")
    print(f"  blocked-split  R2 : {b_mean:.3f}")
    print(f"  leakage (R2 gap)  : {r_mean - b_mean:.3f}")

    assert r_mean > b_mean, "random split should look better; leakage not reproduced"
    print("\n  Random splitting overstates accuracy, as expected.")
    print("  This is why in-country validation must be spatially blocked before")
    print("  it is compared against out-of-country performance.")

    # Leave-one-country-out, including the exclusion of the target.
    print("\n--- leave-one-country-out ---")
    countries = np.array(["SN"] * 40 + ["ML"] * 30 + ["NG"] * 50 + ["GM"] * 20)
    splits = list(leave_one_country_out(countries, exclude="GM"))
    for s in splits:
        n_tr, n_te = s.sizes()
        assert not (countries[s.train] == "GM").any(), "target leaked into training"
        assert not (countries[s.test] == "GM").any(), "target used as a test fold"
        print(f"  hold out {s.name}: train={n_tr:>3}  test={n_te:>3}")

    assert len(splits) == 3, "one split per training country, target excluded"
    print("\n  The Gambia appears in no split, on either side.")


if __name__ == "__main__":
    _selftest()
